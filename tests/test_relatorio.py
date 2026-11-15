"""Lote 5: relatório consolidado do vínculo em PDF."""
from datetime import UTC, date, datetime, timedelta

from app.extensions import db
from app.models import (
    AnexoVersao,
    Ata,
    AtaParticipacao,
    Documento,
    EventoVinculo,
    Marco,
    Parecer,
    VersaoDocumento,
)
from app.services import relatorio
from tests.conftest import login


def _povoar(orientacao, orientador, orientando):
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação & Banca",
        descricao="Entrega do texto completo <revisado>",
        data_prevista=date.today() + timedelta(days=30),
        etapa=20,
        tipo="qualificacao",
        entrega_esperada="documento",
    )
    m2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Capítulo atrasado",
        data_prevista=date.today() - timedelta(days=5),
        status="em_andamento",
        devolvido_em=datetime.now(UTC),
        nota_devolucao="Ajustar seção 2 & referências",
    )
    db.session.add_all([m1, m2])
    db.session.flush()
    ata_fin = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() - timedelta(days=3),
        pauta="Discussão do método",
        deliberacoes="**Refazer** a amostra",
        redigida_por=orientador.id,
        status="finalizada",
    )
    ata_canc = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() + timedelta(days=2),
        pauta="Encontro extra",
        deliberacoes="",
        redigida_por=orientador.id,
        status="cancelada",
        motivo_cancelamento="Conflito de agenda",
    )
    db.session.add_all([ata_fin, ata_canc])
    db.session.flush()
    db.session.add_all([
        AtaParticipacao(ata_id=ata_fin.id, orientacao_id=orientacao.id, presenca="presente"),
        AtaParticipacao(ata_id=ata_canc.id, orientacao_id=orientacao.id, presenca="pendente"),
    ])
    doc = Documento(
        orientacao_id=orientacao.id,
        marco_id=m1.id,
        titulo="Projeto de pesquisa <v1>",
        criado_por=orientando.id,
    )
    db.session.add(doc)
    db.session.flush()
    v1 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        nome_original="p.pdf",
        nome_fisico=f"{doc.id:032x}.pdf",
        tamanho_bytes=1024,
        mimetype="application/pdf",
        enviado_por=orientando.id,
        comentario="Primeira versão enviada",
    )
    v2 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=2,
        nome_original=None,
        nome_fisico=None,
        tamanho_bytes=None,
        mimetype=None,
        enviado_por=orientador.id,
        eh_devolucao=True,
        comentario="Comentário sem arquivo",
    )
    db.session.add_all([v1, v2])
    db.session.flush()
    db.session.add(
        AnexoVersao(
            versao_id=v1.id,
            nome_original="dados & tabela.csv",
            nome_fisico="b" * 32 + ".csv",
            tamanho_bytes=512,
            mimetype="text/csv",
        )
    )
    db.session.add(
        Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=v1.id,
            tipo="documento",
            conteudo="Aprovado com **ressalvas** na seção 3.",
            resultado="aprovado_com_ressalvas",
            emitido_por=orientador.id,
        )
    )
    db.session.add(
        EventoVinculo(
            orientacao_id=orientacao.id,
            tipo="mudanca_titulo",
            fundamentacao="Adequação ao escopo",
            texto_anterior="Título antigo",
            texto_novo="Projeto atualizado",
            registrado_por=orientador.id,
        )
    )
    db.session.commit()


def test_relatorio_gera_pdf(client, orientacao, orientador, orientando):
    _povoar(orientacao, orientador, orientando)
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500


def test_relatorio_de_vinculo_vazio_nao_quebra(client, orientacao):
    """Vínculo recém-criado, sem marco nem ata: as seções dizem 'nenhum', não
    falham."""
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    assert pdf.startswith(b"%PDF")


def test_rota_entrega_pdf_as_partes(client, orientacao, orientador, orientando):
    _povoar(orientacao, orientador, orientando)
    login(client, "orientador@teste.br")
    r = client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF")


def test_orientando_tambem_acessa(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf").status_code == 200


def test_terceiro_nao_acessa(client, orientacao, intruso):
    login(client, "intruso@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf").status_code == 403


def test_link_na_pagina_do_vinculo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}").data.decode()
    assert "relatorio.pdf" in pagina
    assert "Extrato completo do orientando (PDF)" in pagina


def test_atalho_extrato_no_painel_e_em_orientandos(
    client, orientacao, orientador, orientando
):
    login(client, "orientador@teste.br")
    painel_html = client.get("/dashboard").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in painel_html
    assert "Extrato PDF" in painel_html

    orientandos_html = client.get("/orientandos/").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in orientandos_html
    assert "Extrato PDF" in orientandos_html

    # orientando com vínculo encerrado também mantém o acesso ao extrato
    orientacao.status = "concluida"
    db.session.commit()
    orientandos_enc = client.get("/orientandos/").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in orientandos_enc
    assert "concluida" in orientandos_enc


def test_extrato_omite_texto_das_atas_e_filtra_marcos_de_grupo(
    client, orientacao, orientacao2, orientador
):
    import re
    import zlib
    from io import BytesIO

    from reportlab.platypus import Table

    from app.services import linha_tempo
    from app.services.exportacao import _documento_base

    hoje = date.today()
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Tarefa em grupo",
        data_prevista=hoje + timedelta(days=5),
        grupo_id="grp-1",
    )
    m2 = Marco(
        orientacao_id=orientacao2.id,
        titulo="Tarefa em grupo",
        data_prevista=hoje + timedelta(days=5),
        grupo_id="grp-1",
    )
    m_outro = Marco(
        orientacao_id=orientacao2.id,
        titulo="Marco exclusivo do colega",
        data_prevista=hoje + timedelta(days=7),
    )
    db.session.add_all([m1, m2, m_outro])
    db.session.flush()

    ata = Ata(
        tipo="grupo",
        orientador_id=orientador.id,
        data_reuniao=hoje - timedelta(days=2),
        pauta="PAUTA_CONFIDENCIAL_DA_ATA",
        deliberacoes="DELIBERACAO_LONGA_DA_ATA",
        redigida_por=orientador.id,
        status="finalizada",
        marcos=[m1, m2, m_outro],
        participacoes=[
            AtaParticipacao(orientacao_id=orientacao.id, presenca="ausente"),
            AtaParticipacao(orientacao_id=orientacao2.id, presenca="presente"),
        ],
    )
    db.session.add(ata)
    db.session.commit()

    # Linha do tempo filtra pelo vínculo e desduplica títulos de grupo
    ev_reuniao = next(
        e for e in linha_tempo.eventos(orientacao) if e["tipo"] == "reuniao"
    )
    assert ev_reuniao["relacionado"] == "discutiu: Tarefa em grupo"

    # Seção de reuniões no extrato traz apenas a tabela resumida, sem texto das atas
    _, estilos = _documento_base(BytesIO(), "Teste")
    cel = relatorio._estilo_celula(estilos)
    blocos = relatorio._reunioes(orientacao, [ata], estilos, cel)
    tabelas = [b for b in blocos if isinstance(b, Table)]
    assert len(tabelas) == 1
    celula_marcos = tabelas[0]._cellvalues[1][4].text
    assert celula_marcos == "Tarefa em grupo"
    assert tabelas[0]._cellvalues[1][3] == "Ausente"

    # O PDF final não contém os blocos de pauta/deliberações da ata
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    conteudo_pdf = pdf.decode("latin1", errors="ignore")
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.DOTALL):
        try:
            conteudo_pdf += zlib.decompress(m.group(1)).decode("latin1", errors="ignore")
        except zlib.error:
            pass
    assert "PAUTA_CONFIDENCIAL_DA_ATA" not in conteudo_pdf
    assert "DELIBERACAO_LONGA_DA_ATA" not in conteudo_pdf
    assert "Marco exclusivo do colega" not in conteudo_pdf
