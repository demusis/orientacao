import pytest

from tests.conftest import login


def test_ajuda_exige_login(client, app):
    resp = client.get("/ajuda")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


@pytest.mark.parametrize("email", ["admin@teste.br", "orientador@teste.br", "orientando@teste.br"])
def test_ajuda_renderiza_para_todos_os_papeis(client, admin, orientador, orientando, email):
    login(client, email)
    resp = client.get("/ajuda")
    assert resp.status_code == 200
    for trecho in ("Sumário", "Cronograma", "Documentos", "Atas", "Pareceres", "auditoria"):
        assert trecho.encode() in resp.data


def test_ajuda_destaca_o_papel_do_usuario(client, orientando):
    login(client, "orientando@teste.br")
    resp = client.get("/ajuda")
    assert b"seu papel" in resp.data
