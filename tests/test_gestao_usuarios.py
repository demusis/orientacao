from datetime import date

from app.extensions import db
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
            "ativo": "y",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="novo@teste.br").one()
    assert novo.criado_por == admin.id


def test_admin_cria_usuario_com_telefone(client, admin):
    login(client, "admin@teste.br")
    client.post(
        "/admin/usuarios/novo",
        data={
            "nome": "Com Telefone",
            "email": "fone@teste.br",
            "telefone": "(65) 99999-1234",
            "papel": "orientador",
            "ativo": "y",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="fone@teste.br").one()
    assert novo.telefone == "(65) 99999-1234"


def test_telefone_e_opcional(client, admin):
    """Sem telefone informado, a conta é criada e o campo fica vazio."""
    login(client, "admin@teste.br")
    client.post(
        "/admin/usuarios/novo",
        data={
            "nome": "Sem Telefone",
            "email": "semfone@teste.br",
            "telefone": "",
            "papel": "orientando",
            "ativo": "y",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="semfone@teste.br").one()
    assert novo.telefone is None


def test_admin_edita_telefone(client, admin, orientador):
    login(client, "admin@teste.br")
    client.post(
        f"/admin/usuarios/{orientador.id}/editar",
        data={
            "nome": orientador.nome,
            "email": orientador.email,
            "telefone": "11 98888-0000",
            "papel": "orientador",
            "ativo": "y",
        },
        follow_redirects=True,
    )
    assert db.session.get(Usuario, orientador.id).telefone == "11 98888-0000"


def test_admin_exclui_conta_limpa(client, admin):
    login(client, "admin@teste.br")
    client.post(
        "/admin/usuarios/novo",
        data={
            "nome": "Descartável",
            "email": "descartavel@teste.br",
            "papel": "orientando",
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


def _dados_orientando(nome, email):
    return {
        "nome": nome,
        "email": email,
        "modalidade": "mestrado",
        "titulo_projeto": f"Projeto de {nome}",
        "data_inicio": "2026-03-01",
    }


def test_orientador_informa_telefone_do_orientando(client, orientador):
    login(client, "orientador@teste.br")
    dados = _dados_orientando("Calouro Fone", "calourofone@teste.br")
    dados["telefone"] = "(65) 98888-4321"
    client.post("/orientandos/novo", data=dados, follow_redirects=True)
    novo = Usuario.query.filter_by(email="calourofone@teste.br").one()
    assert novo.telefone == "(65) 98888-4321"


def test_orientador_cria_orientando_e_recebe_o_vinculo(client, orientador):
    """O vínculo nasce com a conta e é atribuído a quem a criou."""
    from app.models import Orientacao

    login(client, "orientador@teste.br")
    resp = client.post(
        "/orientandos/novo",
        data=_dados_orientando("Calouro", "calouro@teste.br"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    novo = Usuario.query.filter_by(email="calouro@teste.br").one()
    assert novo.papel == "orientando"
    assert novo.criado_por == orientador.id

    vinculo = Orientacao.query.filter_by(orientando_id=novo.id).one()
    assert vinculo.orientador_id == orientador.id
    assert vinculo.status == "ativa"
    assert vinculo.modalidade == "mestrado"
    assert vinculo.titulo_projeto == "Projeto de Calouro"
    assert LogAuditoria.query.filter_by(acao="criacao_orientacao").count() == 1

    # o vínculo é imediatamente utilizável, sem intermediação do administrador
    assert client.get(f"/orientacoes/{vinculo.id}").status_code == 200


# --- exclusão e desativação são privativas do administrador (20/07/2026) ---


def test_orientador_nao_dispoe_de_exclusao(client, orientador):
    """A rota deixou de existir e a listagem não oferece a ação."""
    login(client, "orientador@teste.br")
    client.post("/orientandos/novo", data=_dados_orientando("Efêmero", "efemero@teste.br"))
    alvo = Usuario.query.filter_by(email="efemero@teste.br").one()

    pagina = client.get("/orientandos/")
    assert b"Excluir" not in pagina.data
    assert client.post(f"/orientandos/{alvo.id}/excluir").status_code == 404
    assert db_existe(alvo.id)


def test_admin_exclui_orientando_descartando_vinculo_vazio(client, admin, orientador):
    """Sem descartar o vínculo vazio nenhuma conta de orientando seria
    excluível, pois o vínculo passou a nascer junto com a conta."""
    from app.models import Orientacao

    login(client, "orientador@teste.br")
    client.post("/orientandos/novo", data=_dados_orientando("Efêmero", "efemero@teste.br"))
    alvo = Usuario.query.filter_by(email="efemero@teste.br").one()
    vinculo_id = Orientacao.query.filter_by(orientando_id=alvo.id).one().id

    client.post("/auth/logout")
    login(client, "admin@teste.br")
    client.post(f"/admin/usuarios/{alvo.id}/excluir", follow_redirects=True)
    assert Usuario.query.filter_by(email="efemero@teste.br").count() == 0
    assert db.session.get(Orientacao, vinculo_id) is None


def test_admin_nao_exclui_conta_com_historico(client, admin, orientador):
    """Um único marco basta para tornar a conta inexcluível."""
    from app.models import Marco, Orientacao

    login(client, "orientador@teste.br")
    client.post("/orientandos/novo", data=_dados_orientando("Ativo", "ativo@teste.br"))
    alvo = Usuario.query.filter_by(email="ativo@teste.br").one()
    vinculo = Orientacao.query.filter_by(orientando_id=alvo.id).one()
    db.session.add(
        Marco(orientacao_id=vinculo.id, titulo="Revisão", data_prevista=date(2026, 9, 1))
    )
    db.session.commit()

    client.post("/auth/logout")
    login(client, "admin@teste.br")
    resp = client.post(f"/admin/usuarios/{alvo.id}/excluir", follow_redirects=True)
    assert "Exclusão recusada".encode() in resp.data
    assert db_existe(alvo.id)
    assert db.session.get(Orientacao, vinculo.id) is not None


def test_desativacao_de_conta_e_privativa_do_admin(client, admin, orientador, orientando):
    """O orientador não dispõe de rota para desativar contas; o admin sim."""
    login(client, "orientador@teste.br")
    assert client.post(f"/admin/usuarios/{orientando.id}/editar").status_code == 403

    client.post("/auth/logout")
    login(client, "admin@teste.br")
    client.post(
        f"/admin/usuarios/{orientando.id}/editar",
        data={
            "nome": orientando.nome,
            "email": orientando.email,
            "papel": "orientando",
        },  # 'ativo' ausente => desmarcado
        follow_redirects=True,
    )
    assert orientando.ativo is False


def test_gestao_de_orientandos_restrita_ao_orientador(client, admin, orientando):
    login(client, "orientando@teste.br")
    assert client.get("/orientandos/").status_code == 403
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    assert client.get("/orientandos/").status_code == 403
