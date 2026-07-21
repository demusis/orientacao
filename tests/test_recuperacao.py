"""Lote 2: recuperação de senha por token assinado.

O que estes testes protegem, além do fluxo feliz: que a tela não revele quem tem
conta, que o link seja de uso único, que expire, e que redefinir a senha encerre
as sessões abertas — o cenário em que a recuperação de fato precisa servir.
"""
import pytest

from app.extensions import db
from app.models import ConfiguracaoEmail, LogAuditoria, Usuario
from app.services import cripto, recuperacao
from app.services import email as email_service

from tests.conftest import login


@pytest.fixture
def envio_habilitado(app):
    config = ConfiguracaoEmail.vigente()
    config.ativo = True
    config.usuario = "sistema@x.br"
    config.senha_cifrada = cripto.cifrar("abcd efgh ijkl mnop")
    db.session.commit()
    return config


@pytest.fixture
def capturar_email(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service, "enviar",
        lambda dest, assunto, corpo: enviados.append((dest, assunto, corpo)) or True,
    )
    return enviados


# --- o token ---


def test_token_ida_e_volta(client, orientador):
    token = recuperacao.gerar_token(orientador)
    assert recuperacao.usuario_do_token(token).id == orientador.id


def test_token_adulterado_nao_valida(client, orientador):
    token = recuperacao.gerar_token(orientador)
    assert recuperacao.usuario_do_token(token[:-4] + "AAAA") is None


def test_token_de_uso_unico(client, orientador):
    """Redefinida a senha, o hash muda e o token emitido antes morre — sem
    coluna de controle."""
    token = recuperacao.gerar_token(orientador)
    orientador.set_senha("outra-senha-forte-123")
    db.session.commit()
    assert recuperacao.usuario_do_token(token) is None


def test_token_de_conta_desativada_nao_valida(client, orientador):
    token = recuperacao.gerar_token(orientador)
    orientador.ativo = False
    db.session.commit()
    assert recuperacao.usuario_do_token(token) is None


def test_token_expirado_nao_valida(client, orientador, monkeypatch):
    token = recuperacao.gerar_token(orientador)
    monkeypatch.setattr(recuperacao, "VALIDADE_SEGUNDOS", -1)
    assert recuperacao.usuario_do_token(token) is None


# --- a tela não revela quem tem conta ---


def test_resposta_identica_para_conta_inexistente(client, orientador, capturar_email):
    r_existe = client.post(
        "/auth/esqueci", data={"email": "orientador@teste.br"}, follow_redirects=True
    )
    r_nao = client.post(
        "/auth/esqueci", data={"email": "ninguem@teste.br"}, follow_redirects=True
    )
    assert "enviamos um link" in r_existe.data.decode()
    assert "enviamos um link" in r_nao.data.decode()
    # só a conta real gera e-mail
    assert len(capturar_email) == 1


def test_conta_desativada_nao_recebe_link(client, orientador, capturar_email):
    orientador.ativo = False
    db.session.commit()
    client.post("/auth/esqueci", data={"email": "orientador@teste.br"})
    assert capturar_email == []


# --- fluxo completo ---


def test_fluxo_redefine_a_senha(client, orientador, capturar_email):
    client.post("/auth/esqueci", data={"email": "orientador@teste.br"})
    _, _, corpo = capturar_email[0]
    caminho = "/auth/redefinir/" + corpo.split("/auth/redefinir/")[1].split("\n")[0]

    client.post(
        caminho,
        data={"nova_senha": "nova-senha-forte-1", "confirmacao": "nova-senha-forte-1"},
        follow_redirects=True,
    )
    db.session.expire(orientador)
    assert orientador.verificar_senha("nova-senha-forte-1")
    assert LogAuditoria.query.filter_by(acao="recuperacao_concluida").count() == 1


def test_token_nao_aparece_na_trilha(client, orientador, capturar_email):
    client.post("/auth/esqueci", data={"email": "orientador@teste.br"})
    registro = LogAuditoria.query.filter_by(acao="recuperacao_solicitada").one()
    # o dados_json, quando existe, não carrega o token
    assert registro.dados_json is None or "eyJ" not in registro.dados_json


# --- encerramento de sessão na troca de senha ---


def test_troca_de_senha_invalida_a_identidade_da_sessao(client, orientador):
    """Quem redefine por suspeita de invasão não pode deixar a sessão do invasor
    viva. A identidade da sessão (`get_id`) inclui um trecho do hash da senha;
    trocada a senha, `load_user` do valor antigo deixa de casar e devolve None.

    Verifica-se pelo `load_user` diretamente, e não por duas requisições: o app
    context de longa duração dos testes faz o Flask-Login cachear o usuário por
    contexto, de modo que a segunda requisição não reinvoca o loader — artefato
    que não existe em produção, onde cada requisição tem contexto próprio."""
    from app.models.user import load_user

    identidade_antiga = orientador.get_id()
    assert load_user(identidade_antiga) is orientador  # sessão válida

    orientador.set_senha("trocada-por-fora-123")
    db.session.commit()

    assert load_user(identidade_antiga) is None  # sessão antiga encerrada
    assert load_user(orientador.get_id()).id == orientador.id  # a nova vale


def test_load_user_tolera_formato_antigo(client, orientador):
    """Sessão gravada antes desta mudança tem `_user_id` só com o id, sem a
    marca. Precisa continuar válida, para a implantação não deslogar todos."""
    from app.models.user import load_user

    assert load_user(str(orientador.id)).id == orientador.id


# --- limite de tentativas cobre este formulário ---


def test_limite_de_tentativas_no_esqueci(client, app, orientador):
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    for _ in range(teto):
        db.session.add(
            LogAuditoria(acao="recuperacao_falha", entidade="usuario",
                         ip="127.0.0.1", dados_json=None)
        )
    db.session.commit()

    r = client.post(
        "/auth/esqueci", data={"email": "x@y.br"}, follow_redirects=True
    )
    assert r.status_code == 429
