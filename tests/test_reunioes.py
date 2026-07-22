from datetime import date

from app.extensions import db
from app.models import Ata, LogAuditoria, Marco, Orientacao
from tests.conftest import _criar_usuario, login


def _criar_ata_grupo(client, orientacoes_ids):
    return client.post(
        "/reunioes/atas/nova",
        data={
            "data_reuniao": "2026-07-18",
            "pauta": "Seminário do grupo de pesquisa",
            "deliberacoes": "Todos devem revisar a metodologia até agosto.",
            "orientacoes": orientacoes_ids,
        },
        follow_redirects=True,
    )


def _criar_tarefa_grupo(client, orientacoes_ids):
    return client.post(
        "/reunioes/tarefas/nova",
        data={
            "titulo": "Revisão de metodologia",
            "descricao": "Conforme seminário",
            "data_prevista": "2026-08-31",
            "tipo": "outro",
            "etapa": 50,
            "orientacoes": orientacoes_ids,
        },
        follow_redirects=True,
    )


def test_ata_de_grupo_e_unica_e_compartilhada(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    resp = _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    assert resp.status_code == 200

    ata = Ata.query.one()
    assert ata.tipo == "grupo"
    assert {o.id for o in ata.orientacoes} == {orientacao.id, orientacao2.id}
    assert LogAuditoria.query.filter_by(acao="criacao_ata_grupo").count() == 1

    # a MESMA ata é visível pelos dois vínculos
    r1 = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}")
    r2 = client.get(f"/orientacoes/{orientacao2.id}/atas/{ata.id}")
    assert r1.status_code == 200 and r2.status_code == 200


def test_finalizacao_unica_vale_para_todos(client, orientacao, orientacao2, orientador, orientando, orientando2):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    assert ata.status == "finalizada"

    client.post("/auth/logout")
    login(client, "orientando2@teste.br")
    resp = client.get(f"/orientacoes/{orientacao2.id}/atas/{ata.id}")
    assert resp.status_code == 200
    assert "finalizada".encode() in resp.data


def test_ata_de_grupo_invisivel_a_nao_participantes(client, orientacao, orientacao2, orientador, intruso):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()

    # terceiro vínculo do mesmo orientador, fora da reunião
    terceiro = _criar_usuario("Orientando E", "orientando3@teste.br", "orientando")
    o3 = Orientacao(
        orientador_id=orientacao.orientador_id,
        orientando_id=terceiro.id,
        modalidade="ic",
        titulo_projeto="Terceiro Projeto",
        data_inicio=date(2026, 3, 1),
    )
    db.session.add(o3)
    db.session.commit()

    client.post("/auth/logout")
    login(client, "orientando3@teste.br")
    assert client.get(f"/orientacoes/{o3.id}/atas/{ata.id}").status_code == 404

    client.post("/auth/logout")
    login(client, "intruso@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}").status_code == 403


def test_reunioes_restrito_ao_papel_orientador(client, admin, orientando):
    login(client, "orientando@teste.br")
    assert client.get("/reunioes/").status_code == 403
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    assert client.get("/reunioes/").status_code == 403


def test_tarefa_de_grupo_replica_marcos_com_grupo_id(client, orientacao, orientacao2, orientador, orientando):
    login(client, "orientador@teste.br")
    resp = _criar_tarefa_grupo(client, [orientacao.id, orientacao2.id])
    assert resp.status_code == 200

    marcos = Marco.query.order_by(Marco.orientacao_id).all()
    assert len(marcos) == 2
    assert marcos[0].grupo_id == marcos[1].grupo_id and marcos[0].grupo_id
    assert {m.orientacao_id for m in marcos} == {orientacao.id, orientacao2.id}
    assert LogAuditoria.query.filter_by(acao="criacao_marco_grupo").count() == 1

    # acompanhamento individual: sinalizar/confirmar em um não afeta o outro
    m1 = next(m for m in marcos if m.orientacao_id == orientacao.id)
    m2 = next(m for m in marcos if m.orientacao_id == orientacao2.id)

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{m1.id}/sinalizar")
    assert m1.conclusao_sinalizada is True
    assert m2.conclusao_sinalizada is False

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{m1.id}/confirmar")
    assert m1.status == "concluido"
    assert m2.status == "pendente"


def test_vinculo_de_outro_orientador_recusado(client, orientacao, orientacao2, orientador, intruso):
    outro = _criar_usuario("Prof. Externo", "externo@teste.br", "orientador")
    alheia = Orientacao(
        orientador_id=outro.id,
        orientando_id=intruso.id,
        modalidade="mestrado",
        titulo_projeto="Projeto Alheio",
        data_inicio=date(2026, 1, 5),
    )
    db.session.add(alheia)
    db.session.commit()

    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, alheia.id])
    assert Ata.query.count() == 0  # seleção fora dos vínculos próprios é inválida

    _criar_tarefa_grupo(client, [orientacao.id, alheia.id])
    assert Marco.query.count() == 0


def test_exige_ao_menos_um_vinculo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _criar_ata_grupo(client, [])
    assert "ao menos um orientando".encode() in resp.data
    assert Ata.query.count() == 0


def test_selecao_unica_gera_ata_individual(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _criar_ata_grupo(client, [orientacao.id])
    assert resp.status_code == 200
    ata = Ata.query.one()
    assert ata.tipo == "individual"
    assert {o.id for o in ata.orientacoes} == {orientacao.id}
    assert LogAuditoria.query.filter_by(acao="criacao_ata").count() == 1


def test_selecao_unica_gera_marco_sem_grupo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _criar_tarefa_grupo(client, [orientacao.id])
    assert resp.status_code == 200
    marco = Marco.query.one()
    assert marco.orientacao_id == orientacao.id
    assert marco.grupo_id is None
    assert LogAuditoria.query.filter_by(acao="criacao_marco").count() == 1
