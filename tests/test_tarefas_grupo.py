"""Gestão de tarefas em grupo pelo módulo de reuniões: listar, editar, excluir.

Criar já existia; faltavam as três. A exclusão segue a filosofia do sistema —
só apaga tarefa sem histórico —, e a edição propaga o conteúdo a todos os
orientandos do grupo, deixando a conclusão individual.
"""
import uuid
from datetime import date, timedelta

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    Documento,
    Marco,
)
from tests.conftest import login


def _tarefa_grupo(orientacao, orientacao2, titulo="Ler capítulo", **kw):
    """Cria uma tarefa em grupo: um marco em cada vínculo, mesmo grupo_id."""
    gid = uuid.uuid4().hex
    marcos = []
    for o in (orientacao, orientacao2):
        m = Marco(
            orientacao_id=o.id, titulo=titulo, grupo_id=gid,
            data_prevista=date.today() + timedelta(days=10), **kw,
        )
        db.session.add(m)
        marcos.append(m)
    db.session.commit()
    return gid, marcos


# --- criar (já existia; confirma o grupo_id compartilhado) ---


def test_criar_tarefa_para_dois_gera_grupo(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    client.post(
        "/reunioes/tarefas/nova",
        data={
            "titulo": "Revisar bibliografia", "tipo": "outro", "descricao": "",
            "data_prevista": "2026-09-30", "etapa": 20,
            "orientacoes": [orientacao.id, orientacao2.id],
        },
    )
    marcos = Marco.query.filter_by(titulo="Revisar bibliografia").all()
    assert len(marcos) == 2
    assert marcos[0].grupo_id and marcos[0].grupo_id == marcos[1].grupo_id


# --- listar ---


def test_indice_lista_tarefas_em_grupo(client, orientacao, orientacao2, orientador):
    _tarefa_grupo(orientacao, orientacao2, "Ler capítulo 3")
    login(client, "orientador@teste.br")
    pagina = client.get("/reunioes/").data.decode()
    assert "Ler capítulo 3" in pagina
    assert "Tarefas atribuídas em grupo" in pagina


# --- editar (propaga a todos) ---


def test_edicao_propaga_a_todos_os_marcos(client, orientacao, orientacao2, orientador):
    gid, marcos = _tarefa_grupo(orientacao, orientacao2, "Antigo")
    login(client, "orientador@teste.br")

    client.post(
        f"/reunioes/tarefas/{gid}/editar",
        data={
            "titulo": "Novo título", "tipo": "outro", "descricao": "desc",
            "data_prevista": "2026-12-01", "etapa": 30,
        },
    )
    for m in Marco.query.filter_by(grupo_id=gid):
        assert m.titulo == "Novo título"
        assert m.data_prevista == date(2026, 12, 1)
        assert m.etapa == 30


def test_conclusao_individual_sobrevive_a_edicao(client, orientacao, orientacao2, orientador):
    """Editar o conteúdo não mexe no status de cada um — um pode estar concluído
    e o outro não."""
    gid, marcos = _tarefa_grupo(orientacao, orientacao2)
    marcos[0].status = "concluido"
    db.session.commit()
    login(client, "orientador@teste.br")

    client.post(
        f"/reunioes/tarefas/{gid}/editar",
        data={"titulo": "X", "tipo": "outro", "descricao": "",
              "data_prevista": "2026-11-01", "etapa": 10},
    )
    m0 = db.session.get(Marco, marcos[0].id)
    m1 = db.session.get(Marco, marcos[1].id)
    assert m0.status == "concluido"
    assert m1.status == "pendente"


# --- excluir: só sem histórico ---


def test_exclui_tarefa_limpa(client, orientacao, orientacao2, orientador):
    gid, _ = _tarefa_grupo(orientacao, orientacao2, "Descartável")
    login(client, "orientador@teste.br")

    client.post(f"/reunioes/tarefas/{gid}/excluir")
    assert Marco.query.filter_by(grupo_id=gid).count() == 0


def test_recusa_exclusao_de_tarefa_concluida(client, orientacao, orientacao2, orientador):
    gid, marcos = _tarefa_grupo(orientacao, orientacao2)
    marcos[0].status = "concluido"  # um só já basta
    db.session.commit()
    login(client, "orientador@teste.br")

    r = client.post(f"/reunioes/tarefas/{gid}/excluir", follow_redirects=True)
    assert "recusada" in r.data.decode().lower()
    assert Marco.query.filter_by(grupo_id=gid).count() == 2  # nada apagado


def test_recusa_exclusao_com_documento_ligado(client, orientacao, orientacao2, orientador):
    gid, marcos = _tarefa_grupo(orientacao, orientacao2)
    doc = Documento(
        orientacao_id=orientacao.id, titulo="Entrega", criado_por=orientacao.orientando_id,
        marco_id=marcos[0].id,
    )
    db.session.add(doc)
    db.session.commit()
    login(client, "orientador@teste.br")

    client.post(f"/reunioes/tarefas/{gid}/excluir")
    assert Marco.query.filter_by(grupo_id=gid).count() == 2


def test_recusa_exclusao_de_tarefa_discutida_em_ata(client, orientacao, orientacao2, orientador):
    gid, marcos = _tarefa_grupo(orientacao, orientacao2)
    ata = Ata(
        orientador_id=orientador.id, data_reuniao=date.today(),
        pauta="p", deliberacoes="d", redigida_por=orientador.id, marcos=[marcos[0]],
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=ata.id, orientacao_id=orientacao.id))
    db.session.commit()
    login(client, "orientador@teste.br")

    client.post(f"/reunioes/tarefas/{gid}/excluir")
    assert Marco.query.filter_by(grupo_id=gid).count() == 2


# --- autorização ---


def test_tarefa_de_outro_orientador_nao_e_acessivel(client, orientacao, orientacao2, admin):
    """Um orientador só gere as próprias tarefas; grupo de outro dá 404."""
    from tests.conftest import _criar_usuario
    outro = _criar_usuario("Outro Orientador", "outro@teste.br", "orientador")
    gid, _ = _tarefa_grupo(orientacao, orientacao2)

    login(client, "outro@teste.br")
    assert client.get(f"/reunioes/tarefas/{gid}/editar").status_code == 404
    assert client.post(f"/reunioes/tarefas/{gid}/excluir").status_code == 404
