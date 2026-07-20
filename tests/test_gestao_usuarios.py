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


def _dados_orientando(nome, email):
    return {
        "nome": nome,
        "email": email,
        "senha": "senha-teste-123",
        "modalidade": "mestrado",
        "titulo_projeto": f"Projeto de {nome}",
        "data_inicio": "2026-03-01",
    }


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


def test_botao_excluir_aparece_para_conta_recem_criada(client, orientador):
    """Regressão: a coluna de ações ficava vazia na listagem."""
    login(client, "orientador@teste.br")
    client.post("/orientandos/novo", data=_dados_orientando("Efêmero", "efemero@teste.br"))
    pagina = client.get("/orientandos/")
    assert b"Excluir" in pagina.data


def test_orientador_exclui_orientando_que_criou(client, orientador):
    """A exclusão remove a conta e o vínculo vazio criado junto com ela."""
    from app.models import Orientacao

    login(client, "orientador@teste.br")
    client.post("/orientandos/novo", data=_dados_orientando("Efêmero", "efemero@teste.br"))
    alvo = Usuario.query.filter_by(email="efemero@teste.br").one()
    vinculo_id = Orientacao.query.filter_by(orientando_id=alvo.id).one().id

    client.post(f"/orientandos/{alvo.id}/excluir", follow_redirects=True)
    assert Usuario.query.filter_by(email="efemero@teste.br").count() == 0
    assert db.session.get(Orientacao, vinculo_id) is None


def test_exclusao_recusada_quando_o_vinculo_tem_registro(client, orientador):
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

    assert b"Excluir" not in client.get("/orientandos/").data
    resp = client.post(f"/orientandos/{alvo.id}/excluir", follow_redirects=True)
    assert "Exclusão recusada".encode() in resp.data
    assert db_existe(alvo.id)
    assert db.session.get(Orientacao, vinculo.id) is not None


def test_orientador_nao_exclui_orientando_de_terceiro(client, orientador, orientando):
    # 'orientando' (fixture) não foi criado pelo orientador (criado_por é nulo)
    login(client, "orientador@teste.br")
    resp = client.post(f"/orientandos/{orientando.id}/excluir")
    assert resp.status_code == 403
    assert db_existe(orientando.id)


def test_orientador_nao_exclui_orientando_vinculado_a_terceiro(
    client, orientador, orientando, orientacao
):
    """Vínculo com outro orientador não é descartável: só o próprio vínculo
    vazio do executor acompanha a conta na exclusão."""
    from tests.conftest import _criar_usuario

    outro = _criar_usuario("Prof. Externo", "externo@teste.br", "orientador")
    orientando.criado_por = orientador.id
    orientacao.orientador_id = outro.id
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
