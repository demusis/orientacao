from app.models import LogAuditoria
from tests.conftest import login


def test_login_valido_redireciona_ao_dashboard(client, orientador):
    resp = login(client, "orientador@teste.br")
    assert resp.status_code == 200
    assert b"Painel" in resp.data


def test_login_invalido_retorna_401_e_audita(client, app, orientador):
    resp = client.post(
        "/auth/login", data={"email": "orientador@teste.br", "senha": "errada"}
    )
    assert resp.status_code == 401
    assert LogAuditoria.query.filter_by(acao="login_falho").count() == 1


def test_login_registra_ultimo_acesso(client, orientador):
    """Base da medição de adesão: só o acesso bem-sucedido marca a conta."""
    assert orientador.ultimo_acesso is None

    client.post(
        "/auth/login", data={"email": "orientador@teste.br", "senha": "errada"}
    )
    assert orientador.ultimo_acesso is None  # tentativa falha não conta

    login(client, "orientador@teste.br")
    assert orientador.ultimo_acesso is not None


def test_usuario_inativo_nao_autentica(client, app, orientador):
    orientador.ativo = False
    from app.extensions import db

    db.session.commit()
    resp = client.post(
        "/auth/login",
        data={"email": "orientador@teste.br", "senha": "senha-teste-123"},
    )
    assert resp.status_code == 403


def test_rota_protegida_exige_login(client, app):
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]
