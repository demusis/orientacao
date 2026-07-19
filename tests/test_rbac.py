import pytest

from tests.conftest import login

ROTAS_ADMIN = [
    "/admin/usuarios",
    "/admin/usuarios/novo",
    "/admin/orientacoes",
    "/admin/orientacoes/nova",
    "/admin/auditoria",
]


@pytest.mark.parametrize("rota", ROTAS_ADMIN)
@pytest.mark.parametrize("email", ["orientador@teste.br", "orientando@teste.br"])
def test_rotas_admin_negadas_a_nao_admins(client, orientador, orientando, rota, email):
    login(client, email)
    assert client.get(rota).status_code == 403


@pytest.mark.parametrize("rota", ROTAS_ADMIN)
def test_rotas_admin_acessiveis_ao_admin(client, admin, rota):
    login(client, "admin@teste.br")
    assert client.get(rota).status_code == 200


def test_orientacao_visivel_apenas_aos_envolvidos(client, orientacao, intruso):
    login(client, "intruso@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}").status_code == 403
    assert client.get(f"/orientacoes/{orientacao.id}/cronograma/").status_code == 403
    assert client.get(f"/orientacoes/{orientacao.id}/documentos/").status_code == 403
    assert client.get(f"/orientacoes/{orientacao.id}/atas").status_code == 403


def test_orientacao_visivel_ao_orientando_vinculado(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}").status_code == 200


def test_admin_acessa_qualquer_orientacao(client, orientacao, admin):
    login(client, "admin@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}").status_code == 200


def test_orientando_nao_cria_marco(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    resp = client.get(f"/orientacoes/{orientacao.id}/cronograma/novo")
    assert resp.status_code == 403


def test_orientando_nao_cria_ata_nem_parecer(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/atas/nova").status_code == 403
    assert client.get(f"/orientacoes/{orientacao.id}/pareceres/novo").status_code == 403
