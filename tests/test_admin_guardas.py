from app.models import LogAuditoria, Usuario

from tests.conftest import _criar_usuario, login


def _editar(client, usuario, papel, ativo=True):
    dados = {
        "nome": usuario.nome,
        "email": usuario.email,
        "papel": papel,
        "senha": "",
    }
    if ativo:
        dados["ativo"] = "y"
    return client.post(
        f"/admin/usuarios/{usuario.id}/editar", data=dados, follow_redirects=True
    )


def test_admin_nao_altera_o_proprio_papel(client, admin):
    login(client, "admin@teste.br")
    resp = _editar(client, admin, papel="orientador")
    assert "não pode alterar o próprio papel".encode() in resp.data
    assert admin.papel == "admin"
    assert LogAuditoria.query.filter_by(acao="autodespromocao_recusada").count() == 1


def test_admin_nao_desativa_a_propria_conta(client, admin):
    login(client, "admin@teste.br")
    _editar(client, admin, papel="admin", ativo=False)
    assert admin.ativo is True


def test_ultimo_admin_ativo_nao_e_despromovido(client, admin):
    segundo = _criar_usuario("Admin Inativo", "admin2@teste.br", "admin")
    segundo.ativo = False
    from app.extensions import db

    db.session.commit()

    login(client, "admin@teste.br")
    # admin (único ativo) tenta despromover a si — já coberto; tenta reativar/despromover o inativo é permitido
    resp = _editar(client, segundo, papel="orientador", ativo=True)
    assert segundo.papel == "orientador"  # alvo estava inativo; não reduz admins ativos
    assert resp.status_code == 200


def test_despromocao_permitida_com_dois_admins_ativos(client, admin):
    segundo = _criar_usuario("Admin B", "admin2@teste.br", "admin")

    login(client, "admin@teste.br")
    _editar(client, segundo, papel="orientador")
    assert segundo.papel == "orientador"
    assert Usuario.query.filter_by(papel="admin", ativo=True).count() == 1
