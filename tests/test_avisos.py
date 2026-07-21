"""Avisos diários de pendência.

Duas coisas importam aqui e são fáceis de errar em silêncio: **cada pessoa
receber uma só mensagem**, com tudo o que lhe cabe, e o disparo **acontecer uma
única vez por dia**, mesmo com requisições concorrentes.
"""
import json
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoEmail,
    Documento,
    LogAuditoria,
    Marco,
    VersaoDocumento,
)
from app.services import avisos, cripto
from app.services import email as email_service

from tests.conftest import login


@pytest.fixture
def envio_habilitado(app):
    config = ConfiguracaoEmail.vigente()
    config.ativo = True
    config.usuario = "ariadne.sistema@gmail.com"
    config.senha_cifrada = cripto.cifrar("abcd efgh ijkl mnop")
    db.session.commit()
    return config


@pytest.fixture
def lote_capturado(monkeypatch):
    """Substitui o envio real: a suíte não pode depender de rede."""
    capturado = []

    def falso_lote(mensagens):
        capturado.extend(mensagens)
        return [d for d, _, _ in mensagens], []

    monkeypatch.setattr(email_service, "enviar_lote", falso_lote)
    return capturado


def _marco_atrasado(orientacao, dias=3):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Entregar capítulo 1",
        data_prevista=date.today() - timedelta(days=dias),
    )
    db.session.add(m)
    db.session.commit()
    return m


def _marco_sinalizado(orientacao):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Coleta concluída",
        data_prevista=date.today() + timedelta(days=10),
        conclusao_sinalizada=True,
    )
    db.session.add(m)
    db.session.commit()
    return m


def _versao_sem_parecer(orientacao):
    doc = Documento(
        orientacao_id=orientacao.id,
        titulo="Projeto de pesquisa",
        criado_por=orientacao.orientando_id,
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        nome_original="p.pdf",
        nome_fisico="a" * 32 + ".pdf",
        tamanho_bytes=1024,
        mimetype="application/pdf",
        enviado_por=orientacao.orientando_id,
    )
    db.session.add(v)
    db.session.commit()
    return v


def _ata_rascunho_velha(orientacao, orientador, dias=30):
    a = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() - timedelta(days=dias),
        pauta="p",
        deliberacoes="d",
        redigida_por=orientador.id,
    )
    db.session.add(a)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=a.id, orientacao_id=orientacao.id))
    db.session.commit()
    return a


# --- categorias ---


def test_marco_atrasado_vai_para_o_orientando(client, orientacao, orientando):
    _marco_atrasado(orientacao)
    coletado = avisos.coletar()
    assert orientando in coletado
    assert "Marcos com prazo vencido" in coletado[orientando]


def test_marco_no_prazo_nao_gera_aviso(client, orientacao, orientando):
    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Futuro",
            data_prevista=date.today() + timedelta(days=5),
        )
    )
    db.session.commit()
    assert avisos.coletar() == {}


def test_categorias_do_orientador(client, orientacao, orientador, orientando):
    _marco_sinalizado(orientacao)
    _versao_sem_parecer(orientacao)
    _ata_rascunho_velha(orientacao, orientador)

    secoes = avisos.coletar()[orientador]
    assert "Entregas aguardando sua confirmação" in secoes
    assert "Entregas aguardando parecer" in secoes
    assert "Atas em rascunho" in secoes


def test_uma_mensagem_por_pessoa_reunindo_tudo(
    client, orientacao, orientador, orientando, envio_habilitado, lote_capturado
):
    """Quatro pendências do orientador precisam virar UM e-mail: quatro
    mensagens no mesmo minuto seriam lidas como ruído e ignoradas."""
    _marco_atrasado(orientacao)
    _marco_sinalizado(orientacao)
    _versao_sem_parecer(orientacao)
    _ata_rascunho_velha(orientacao, orientador)

    resumo = avisos.enviar_pendentes()
    assert resumo["destinatarios"] == 2  # orientador e orientando
    assert len(lote_capturado) == 2

    para_orientador = [m for m in lote_capturado if m[0] == orientador.email][0]
    corpo = para_orientador[2]
    assert corpo.count("aguardando sua confirmação") == 1
    assert "aguardando parecer" in corpo
    assert "Atas em rascunho" in corpo


def test_vinculo_encerrado_nao_gera_aviso(client, orientacao, orientando):
    _marco_atrasado(orientacao)
    orientacao.status = "concluida"
    db.session.commit()
    assert avisos.coletar() == {}


# --- trava do disparo diário ---


def test_disparo_ocorre_uma_vez_por_dia(client, envio_habilitado):
    assert avisos.marcar_dia_como_enviado() is True
    db.session.commit()
    assert avisos.marcar_dia_como_enviado() is False


def test_novo_dia_libera_o_disparo(client, envio_habilitado):
    config = ConfiguracaoEmail.vigente()
    config.avisos_enviados_em = date.today() - timedelta(days=1)
    db.session.commit()
    assert avisos.marcar_dia_como_enviado() is True


# --- gatilho por requisição ---


def test_requisicao_dispara_e_registra(
    app, client, orientacao, orientando, envio_habilitado, lote_capturado
):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)

    client.get("/auth/login")

    assert len(lote_capturado) == 1
    registro = LogAuditoria.query.filter_by(acao="envio_avisos").one()
    dados = json.loads(registro.dados_json)
    assert dados["destinatarios"] == 1
    assert ConfiguracaoEmail.vigente().avisos_enviados_em == date.today()


def test_segunda_requisicao_do_dia_nao_reenvia(
    app, client, orientacao, orientando, envio_habilitado, lote_capturado
):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)

    client.get("/auth/login")
    client.get("/auth/login")
    client.get("/auth/login")

    assert len(lote_capturado) == 1
    assert LogAuditoria.query.filter_by(acao="envio_avisos").count() == 1


def test_envio_desabilitado_nao_dispara(app, client, orientacao, orientando, lote_capturado):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)  # há pendência, mas o envio está desligado

    client.get("/auth/login")

    assert lote_capturado == []
    assert LogAuditoria.query.filter_by(acao="envio_avisos").count() == 0


def test_falha_no_disparo_nao_derruba_a_requisicao(
    app, client, orientacao, orientando, envio_habilitado, monkeypatch
):
    """A pessoa que abriu a página nada tem a ver com o envio: se ele estourar,
    a requisição dela precisa seguir normalmente."""
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)
    monkeypatch.setattr(
        avisos, "enviar_pendentes",
        lambda: (_ for _ in ()).throw(RuntimeError("erro inesperado")),
    )

    resposta = client.get("/auth/login")
    assert resposta.status_code == 200


def test_tela_mostra_falhas_do_ultimo_disparo(client, admin, envio_habilitado):
    from app.services import auditoria

    auditoria.registrar(
        "envio_avisos", "configuracao_email", 1,
        {"destinatarios": 2, "itens": 3, "enviados": ["a@x.br"], "falhas": ["b@x.br"]},
    )
    db.session.commit()

    login(client, "admin@teste.br")
    pagina = client.get("/admin/email").data.decode()
    assert "b@x.br" in pagina
    assert "não foi(ram) entregue(s)" in pagina or "entregue" in pagina
