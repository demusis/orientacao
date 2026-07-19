from app.models import LogAuditoria, Usuario

from tests.conftest import login


def test_admin_cria_usuario_com_autor_registrado(client, admin):
    login(client, "admin@teste.br")
    client.post(
        "/admin/usuarios/novo",
        data={
            "nome": "Novo Orientador",
            "email": "novo@teste.br",
            "papel": "orientador",
            "senha": "senha-teste-123",
            "ativo": "y",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="novo@teste.br").one()
    assert novo.criado_por == admin.id


def test_admin_exclui_conta_limpa(client, admin):
    login(client, "admin@teste.br")
    client.post(
        "/admin/usuarios/novo",
        data={
            "nome": "Descartável",
            "email": "descartavel@teste.br",
            "papel": "orientando",
            "senha": "senha-teste-123",
            "ativo": "y",
        },
    )
    alvo = Usuario.query.filter_by(email="descartavel@teste.br").one()
    client.post(f"/admin/usuarios/{alvo.id}/excluir", follow_redirects=True)
    assert Usuario.query.filter_by(email="descartavel@teste.br").count() == 0
    assert LogAuditoria.query.filter_by(acao="exclusao_usuario").count() == 1


def test_admin_nao_exclui_conta_com_vinculo(client, admin, orientacao, orientador):
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/usuarios/{orientador.id}/excluir", follow_redirects=True
    )
    assert "Exclusão recusada".encode() in resp.data
    assert db_existe(orientador.id)
    assert LogAuditoria.query.filter_by(acao="exclusao_recusada").count() == 1


def db_existe(usuario_id):
    from app.extensions import db

    return db.session.get(Usuario, usuario_id) is not None


def test_admin_nao_exclui_a_propria_conta(client, admin):
    login(client, "admin@teste.br")
    client.post(f"/admin/usuarios/{admin.id}/excluir", follow_redirects=True)
    assert db_existe(admin.id)
    assert LogAuditoria.query.filter_by(acao="autoexclusao_recusada").count() == 1


def test_orientador_cria_orientando(client, orientador):
    login(client, "orientador@teste.br")
    resp = client.post(
        "/orientandos/novo",
        data={
            "nome": "Calouro",
            "email": "calouro@teste.br",
            "senha": "senha-teste-123",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    novo = Usuario.query.filter_by(email="calouro@teste.br").one()
    assert novo.papel == "orientando"
    assert novo.criado_por == orientador.id


def test_orientador_exclui_orientando_que_criou(client, orientador):
    login(client, "orientador@teste.br")
    client.post(
        "/orientandos/novo",
        data={"nome": "Efêmero", "email": "efemero@teste.br", "senha": "senha-teste-123"},
    )
    alvo = Usuario.query.filter_by(email="efemero@teste.br").one()
    client.post(f"/orientandos/{alvo.id}/excluir", follow_redirects=True)
    assert Usuario.query.filter_by(email="efemero@teste.br").count() == 0


def test_orientador_nao_exclui_orientando_de_terceiro(client, orientador, orientando):
    # 'orientando' (fixture) não foi criado pelo orientador (criado_por é nulo)
    login(client, "orientador@teste.br")
    resp = client.post(f"/orientandos/{orientando.id}/excluir")
    assert resp.status_code == 403
    assert db_existe(orientando.id)


def test_orientador_nao_exclui_orientando_com_vinculo(client, orientador, orientando, orientacao):
    from app.extensions import db

    orientando.criado_por = orientador.id  # criado por ele, mas já vinculado
    db.session.commit()
    login(client, "orientador@teste.br")
    resp = client.post(f"/orientandos/{orientando.id}/excluir", follow_redirects=True)
    assert "Exclusão recusada".encode() in resp.data
    assert db_existe(orientando.id)


def test_gestao_de_orientandos_restrita_ao_orientador(client, admin, orientando):
    login(client, "orientando@teste.br")
    assert client.get("/orientandos/").status_code == 403
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    assert client.get("/orientandos/").status_code == 403
