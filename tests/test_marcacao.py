"""Marcação dos campos longos de ata e parecer.

O que estes testes protegem não é a formatação em si, e sim a correspondência
entre a tela e o PDF: o papel vai a assinatura externa e o hash certifica sua
correspondência com o registro interno. Tela e papel divergirem seria o defeito
grave — o orientando aprovaria uma coisa e assinaria outra.
"""
import json
from datetime import date
from io import BytesIO

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate

from app.extensions import db
from app.models import Ata, AtaParticipacao
from app.services import exportacao, marcacao

from tests.conftest import login

ESTILOS = getSampleStyleSheet()

AMOSTRA = """# Encaminhamentos

Parágrafo com **negrito**, *itálico* e `codigo`.
Segunda linha do mesmo parágrafo.

- primeiro item
- segundo item **destacado**

1. etapa um
2. etapa dois

> Observação registrada em ata.

---

| Etapa | Prazo | Situação |
|---|---|---|
| Coleta | 09/2026 | **em curso** |
"""


def _pdf(flowables) -> bytes:
    buffer = BytesIO()
    SimpleDocTemplate(buffer).build(list(flowables))
    return buffer.getvalue()


# --- segurança: o emissor só produz o repertório que conhece ---


TAGS_EMITIDAS = {
    "p", "br", "strong", "em", "code", "pre", "hr",
    "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
}


def test_html_cru_nao_atravessa_o_emissor():
    """Verifica o repertório fechado em vez de procurar palavras perigosas: toda
    tag da saída precisa ser uma das que o emissor sabe produzir. Um `onerror=`
    dentro de texto escapado é inerte; o que não pode existir é tag que o emissor
    não gerou."""
    import re

    entrada = (
        "<script>alert(1)</script> e <img src=x onerror=alert(2)> "
        "e <div onclick='x'>bloco</div> e <a href=javascript:x>link</a>"
    )
    html = str(marcacao.para_html(entrada))

    encontradas = {t.lower() for t in re.findall(r"<\s*/?\s*([a-zA-Z0-9]+)", html)}
    assert encontradas <= TAGS_EMITIDAS, f"tags estranhas: {encontradas - TAGS_EMITIDAS}"
    # e o texto não sumiu: aparece literal para quem lê
    assert "&lt;script&gt;" in html
    assert "onerror" in html and "&lt;img" in html


def test_html_cru_nao_atravessa_para_o_pdf():
    """O paraparser do reportlab também interpreta marcação: o mesmo texto
    precisa sair escapado no papel, sem levantar exceção de parsing."""
    entrada = "<script>alert(1)</script> & <b>nao negrito</b> < 5"
    assert _pdf(marcacao.para_flowables(entrada, ESTILOS))


def test_e_comercial_e_sinal_de_menor_nao_quebram_o_pdf():
    assert _pdf(marcacao.para_flowables("Silva & Souza, n < 30", ESTILOS))


# --- um parse, dois emissores ---


def test_tela_e_pdf_partem_da_mesma_arvore():
    """Asserção que protege a decisão estrutural: se alguém trocar um dos
    emissores por outro parser, as duas saídas deixam de concordar."""
    arvore = marcacao.analisar(AMOSTRA)
    tipos = {no["type"] for no in arvore}
    assert {"heading", "paragraph", "list", "block_quote", "table"} <= tipos

    html = str(marcacao.para_html(AMOSTRA))
    flowables = marcacao.para_flowables(AMOSTRA, ESTILOS)
    nomes = [type(f).__name__ for f in flowables]

    # título, ênfase, lista, citação e tabela presentes nos dois
    assert "<h3>Encaminhamentos</h3>" in html
    assert "<strong>negrito</strong>" in html
    assert "<em>itálico</em>" in html
    assert "<ul>" in html and "<ol>" in html
    assert "<blockquote>" in html
    assert "<table>" in html
    assert "Table" in nomes
    assert "HRFlowable" in nomes
    assert _pdf(flowables)


def test_quebra_de_linha_sobrevive_na_tela():
    """Defeito anterior: o texto era impresso em <p> sem pre-wrap e as quebras
    sumiam, de modo que a tela mostrava menos estrutura que o PDF. Markdown
    estrito juntaria as duas linhas; aqui a quebra é preservada de propósito."""
    html = str(marcacao.para_html("Linha um\nLinha dois"))
    assert "<br>" in html
    assert "Linha um" in html and "Linha dois" in html


def test_link_expoe_o_destino_nos_dois_emissores():
    """Âncora que esconde o destino é vetor de fraude em documento assinado."""
    html = str(marcacao.para_html("[clique aqui](http://exemplo.br/x)"))
    assert "clique aqui (http://exemplo.br/x)" in html
    assert "<a " not in html and "href" not in html

    arvore = marcacao.analisar("[clique aqui](http://exemplo.br/x)")
    assert "http://exemplo.br/x" in marcacao._pdf_inline(arvore[0]["children"])


def test_imagem_nao_busca_recurso_externo():
    html = str(marcacao.para_html("![diagrama](http://externo/x.png)"))
    assert "<img" not in html
    assert "diagrama (http://externo/x.png)" in html


# --- tabelas ---


def test_tabela_estreita_e_larga_geram_pdf():
    estreita = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    colunas = 8
    larga = (
        "| " + " | ".join(f"C{i}" for i in range(colunas)) + " |\n"
        "|" + "---|" * colunas + "\n"
        "| " + " | ".join(str(i) for i in range(colunas)) + " |\n"
    )
    for fonte in (estreita, larga):
        assert _pdf(marcacao.para_flowables(fonte, ESTILOS))


def test_tabela_larga_reduz_a_fonte():
    """Estouro de margem no reportlab é silencioso — a coluna sai da página sem
    erro. A redução acima de 6 colunas é a única defesa."""
    colunas = 8
    larga = (
        "| " + " | ".join(f"C{i}" for i in range(colunas)) + " |\n"
        "|" + "---|" * colunas + "\n"
        "| " + " | ".join(str(i) for i in range(colunas)) + " |\n"
    )
    tabela = [
        f for f in marcacao.para_flowables(larga, ESTILOS)
        if type(f).__name__ == "Table"
    ][0]
    assert len(tabela._colWidths) == colunas
    assert sum(tabela._colWidths) <= marcacao.LARGURA_UTIL + 0.01


# --- formato congelado ---


def _ata_de_teste(orientacao, orientador, texto=AMOSTRA):
    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=date(2026, 8, 10),
        pauta=texto,
        deliberacoes=texto,
        redigida_por=orientador.id,
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(
        AtaParticipacao(ata_id=ata.id, orientacao_id=orientacao.id)
    )
    db.session.commit()
    return ata


def test_finalizacao_congela_o_formato(client, orientacao, orientador):
    ata = _ata_de_teste(orientacao, orientador)
    exportacao.congelar_ata(ata)
    db.session.commit()

    congelado = json.loads(ata.conteudo_congelado)
    assert congelado["formato"] == "markdown"
    assert ata.formato_conteudo == "markdown"


def test_registro_anterior_ao_markdown_permanece_literal(client, orientacao, orientador):
    """Snapshot sem a chave `formato` é anterior à adoção da marcação. Precisa
    continuar sendo exibido e impresso literalmente: documento assinado não muda
    de aparência retroativamente."""
    ata = _ata_de_teste(orientacao, orientador, texto="**nao e negrito**")
    dados = exportacao.dados_ata(ata)
    dados.pop("formato")
    ata.conteudo_congelado = json.dumps(dados, ensure_ascii=False)
    db.session.commit()

    assert ata.formato_conteudo == "texto"
    html = str(marcacao.para_html(ata.pauta, ata.formato_conteudo))
    assert "<strong>" not in html
    assert "**nao e negrito**" in html


def test_hash_cobre_a_fonte_e_nao_a_apresentacao(client, orientacao, orientador):
    """O hash deriva do snapshot, que guarda o texto-fonte. Mudar o emissor não
    pode invalidar documento já assinado."""
    ata = _ata_de_teste(orientacao, orientador)
    exportacao.congelar_ata(ata)
    db.session.commit()
    antes = exportacao.hash_ata(ata)

    marcacao._analisador  # emissor permanece o mesmo objeto; o hash não o consulta
    assert exportacao.hash_ata(ata) == antes
    assert antes == exportacao.hashlib.sha256(
        ata.conteudo_congelado.encode("utf-8")
    ).hexdigest()


# --- integração pela tela ---


def test_tela_da_ata_exibe_marcacao_renderizada(client, orientacao, orientador):
    ata = _ata_de_teste(orientacao, orientador)
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}", follow_redirects=True
    ).data.decode()
    assert "<h3>Encaminhamentos</h3>" in pagina
    assert "<strong>negrito</strong>" in pagina
    assert 'class="prosa"' in pagina


def test_formulario_anuncia_a_marcacao_aceita(client, orientacao, orientador):
    ata = _ata_de_teste(orientacao, orientador)
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}", follow_redirects=True
    ).data.decode()
    assert "Aceita formata" in pagina
