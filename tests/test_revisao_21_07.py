"""Regressões da revisão de código de 21/07/2026.

Cada teste aqui nasceu de um defeito confirmado por revisão sobre código que já
estava em produção. Os comentários dizem qual era o defeito, porque a asserção
sozinha não explica por que ela importa.
"""
import json
from datetime import date, timedelta

import pytest
from reportlab.lib.styles import getSampleStyleSheet

from app.extensions import db
from app.models import Ata, AtaParticipacao, ConfiguracaoEmail, LogAuditoria, Marco
from app.services import avisos, cripto, marcacao
from app.services import email as email_service

ESTILOS = getSampleStyleSheet()


def _texto_do_pdf(flowables) -> str:
    return " ".join(str(f.text) for f in flowables if hasattr(f, "text"))


# --- markdown: tela e PDF não podem divergir ---


def test_bloco_dentro_de_item_de_lista_chega_ao_pdf():
    """`_pdf_lista` só tratava block_text/paragraph/list e DESCARTAVA o resto.
    Uma citação dentro de um item aparecia na tela e sumia do PDF assinado —
    a divergência que o módulo promete impedir."""
    fonte = "- Encaminhamento\n\n  > texto da resolucao citada\n"
    html = str(marcacao.para_html(fonte))
    pdf = _texto_do_pdf(marcacao.para_flowables(fonte, ESTILOS))

    assert "resolucao citada" in html
    assert "resolucao citada" in pdf


def test_titulo_dentro_de_item_de_lista_chega_ao_pdf():
    fonte = "- Item\n\n  ### Subtitulo dentro do item\n"
    assert "Subtitulo dentro do item" in _texto_do_pdf(
        marcacao.para_flowables(fonte, ESTILOS)
    )


def test_rotulo_de_link_com_enfase_nao_some():
    """`_texto_dos_filhos` lia só a chave `raw` dos filhos diretos; nós de
    ênfase guardam o texto em `children`, de modo que `[**o edital** aqui](url)`
    produzia " aqui (url)" — palavras apagadas de um documento imutável."""
    fonte = "[**o edital** aqui](http://x.br/a)"
    html = str(marcacao.para_html(fonte))
    pdf = _texto_do_pdf(marcacao.para_flowables(fonte, ESTILOS))

    for saida in (html, pdf):
        assert "o edital" in saida
        assert "http://x.br/a" in saida


def test_rotulo_de_link_com_codigo_nao_some():
    fonte = "[veja `config.py` aqui](http://x.br/a)"
    assert "config.py" in str(marcacao.para_html(fonte))


# --- formato: rascunho antigo não vira markdown ---


def _ata(orientacao, orientador, **kw):
    a = Ata(
        orientador_id=orientador.id,
        data_reuniao=date(2026, 8, 1),
        pauta="# de participantes: 4",
        deliberacoes="d",
        redigida_por=orientador.id,
        **kw,
    )
    db.session.add(a)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=a.id, orientacao_id=orientacao.id))
    db.session.commit()
    return a


def test_rascunho_marcado_como_texto_nao_e_reinterpretado(
    client, orientacao, orientador
):
    """Rascunho anterior à adoção do markdown recebe formato 'texto' pela
    migração. Antes, todo rascunho sem snapshot era suposto markdown, e uma
    pauta com '# de participantes: 4' perdia o '#' — perda que virava
    permanente ao finalizar."""
    ata = _ata(orientacao, orientador, formato="texto")

    assert ata.formato_conteudo == "texto"
    html = str(marcacao.para_html(ata.pauta, ata.formato_conteudo))
    assert "# de participantes: 4" in html
    assert "<h3>" not in html


def test_rascunho_novo_continua_em_markdown(client, orientacao, orientador):
    assert _ata(orientacao, orientador).formato_conteudo == "markdown"


def test_snapshot_prevalece_sobre_a_coluna(client, orientacao, orientador):
    """Congelado o registro, quem manda é o snapshot: é ele que o PDF imprime."""
    ata = _ata(orientacao, orientador, formato="markdown")
    ata.conteudo_congelado = json.dumps({"formato": "texto"})
    db.session.commit()
    assert ata.formato_conteudo == "texto"


# --- avisos ---


@pytest.fixture
def envio_habilitado(app):
    config = ConfiguracaoEmail.vigente()
    config.ativo = True
    config.usuario = "sistema@x.br"
    config.senha_cifrada = cripto.cifrar("abcd efgh ijkl mnop")
    db.session.commit()
    return config


@pytest.fixture
def lote_ok(monkeypatch):
    monkeypatch.setattr(
        email_service, "enviar_lote", lambda m: ([d for d, *_ in m], [])
    )


def _marco_atrasado(orientacao, titulo="Atrasado"):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo=titulo,
        data_prevista=date.today() - timedelta(days=3),
    )
    db.session.add(m)
    db.session.commit()
    return m


def test_conta_desativada_nao_recebe(client, orientacao, orientando):
    """Conta desativada continuava recebendo nomes de orientandos, títulos de
    projeto e datas — dado pessoal trafegando para quem perdeu o acesso, sem
    meio de fazer parar."""
    _marco_atrasado(orientacao)
    assert orientando in avisos.coletar()

    orientando.ativo = False
    db.session.commit()
    assert avisos.coletar() == {}


def test_ata_de_vinculo_encerrado_nao_gera_aviso(client, orientacao, orientador):
    """Sem o filtro de vínculo ativo, ata em rascunho de vínculo encerrado
    gerava aviso diário perpétuo, mandando finalizar algo cuja tela já não
    oferece caminho."""
    ata = _ata(orientacao, orientador)
    ata.data_reuniao = date.today() - timedelta(days=40)
    db.session.commit()
    assert orientador in avisos.coletar()

    orientacao.status = "concluida"
    db.session.commit()
    assert avisos.coletar() == {}


def test_falha_parcial_reenvia_apenas_a_quem_faltou(
    client, orientacao, orientador, orientando, envio_habilitado, monkeypatch
):
    """Antes, qualquer sucesso encerrava o dia e o destinatário que falhou
    ficava sem aviso. Agora o dia só encerra sem falhas, e a repetição não
    duplica para quem já recebeu."""
    _marco_atrasado(orientacao)  # destina-se ao orientando
    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Sinalizado",
            data_prevista=date.today() + timedelta(days=5),
            conclusao_sinalizada=True,
        )
    )
    db.session.commit()  # destina-se ao orientador

    def parcial(mensagens):
        ok = [d for d, *_ in mensagens if d == orientando.email]
        ruim = [d for d, *_ in mensagens if d != orientando.email]
        return ok, ruim

    monkeypatch.setattr(email_service, "enviar_lote", parcial)
    primeiro = avisos.disparar_se_devido()
    assert set(primeiro["enviados"]) == {orientando.email}
    assert set(primeiro["falhas"]) == {orientador.email}
    assert ConfiguracaoEmail.vigente().avisos_enviados_em != date.today()

    ConfiguracaoEmail.vigente().avisos_tentados_em = (
        avisos._agora() - avisos.INTERVALO_ENTRE_TENTATIVAS - timedelta(minutes=1)
    )
    db.session.commit()

    tentados = []

    def registrar_e_entregar(mensagens):
        tentados.extend(d for d, *_ in mensagens)
        return [d for d, *_ in mensagens], []

    monkeypatch.setattr(email_service, "enviar_lote", registrar_e_entregar)
    segundo = avisos.disparar_se_devido()

    assert tentados == [orientador.email]  # o orientando NÃO foi reavisado
    assert segundo["falhas"] == []
    assert ConfiguracaoEmail.vigente().avisos_enviados_em == date.today()


def test_reserva_persistida_antes_da_rede(
    client, orientacao, orientando, envio_habilitado, monkeypatch
):
    """A trava de escrita do SQLite não pode ficar aberta durante o SMTP: outra
    requisição que gravasse esperaria pela rede e poderia receber
    `database is locked`."""
    _marco_atrasado(orientacao)
    visto = {}

    def espiar(mensagens):
        visto["tentado_em"] = db.session.execute(
            db.text("SELECT avisos_tentados_em FROM configuracao_email WHERE id = 1")
        ).scalar()
        return [d for d, *_ in mensagens], []

    monkeypatch.setattr(email_service, "enviar_lote", espiar)
    avisos.disparar_se_devido()

    assert visto["tentado_em"] is not None


def test_auditoria_do_disparo_nao_tem_autor(
    app, client, orientacao, orientando, envio_habilitado, lote_ok
):
    """A trilha atribuía o envio em massa a quem por acaso abrisse uma página."""
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)

    client.get("/auth/login")

    registro = LogAuditoria.query.filter_by(acao="envio_avisos").one()
    assert registro.usuario_id is None
    assert registro.ip is None


def test_link_do_email_nao_vem_do_cabecalho_host(app):
    """`request.url_root` vinha do cabeçalho Host, controlado pelo cliente: uma
    requisição forjada no instante do disparo apontaria o botão de todos os
    e-mails do dia para o domínio do atacante."""
    app.config["URL_BASE"] = ""
    with app.test_request_context("/", headers={"Host": "sitio-falso.exemplo"}):
        assert avisos.endereco_do_sistema() == ""

    app.config["URL_BASE"] = "https://legitimo.br"
    with app.test_request_context("/", headers={"Host": "sitio-falso.exemplo"}):
        assert avisos.endereco_do_sistema() == "https://legitimo.br"
