"""Painel separa "a fazer" de "devolvidas", com o que cada tarefa espera; o
documento diz a que tarefa pertence."""
from datetime import UTC, datetime

from app.extensions import db
from tests.conftest import login
from tests.test_tarefa_guiada import _doc, _marco


def test_painel_separa_a_fazer_de_devolvidas(client, orientacao, orientando):
    _marco(orientacao, titulo="Nova entrega", entrega_esperada="documento")
    _marco(orientacao, titulo="Volta corrigir", devolvido_em=datetime.now(UTC),
           status="em_andamento", nota_devolucao="Reveja as tabelas")
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()
    a_fazer = pagina.index("Tarefas a fazer")
    devolvidas = pagina.index("Devolvidas para você corrigir")
    assert "Reveja as tabelas" in pagina[devolvidas:a_fazer]
    assert "Nova entrega" in pagina[a_fazer:]
    assert "Volta corrigir" not in pagina[a_fazer:]
    assert "entregar documento" in pagina[a_fazer:]


def test_painel_mostra_o_texto_a_revisar(client, orientacao, orientando):
    base = _doc(orientacao, orientacao.orientando_id, titulo="Projeto de mestrado")
    _marco(orientacao, titulo="Revisar projeto", entrega_esperada="revisao",
           documento_base_id=base.id)
    login(client, "orientando@teste.br")
    assert "revisar: Projeto de mestrado" in client.get("/dashboard").data.decode()


def test_documento_mostra_a_tarefa_e_a_revisao(client, orientacao, orientando):
    tarefa = _marco(orientacao, titulo="Capítulo 1")
    doc = _doc(orientacao, orientacao.orientando_id, titulo="Cap1", marco=tarefa)
    revisao = _marco(orientacao, titulo="Revisar Cap1", entrega_esperada="revisao",
                     documento_base_id=doc.id)
    db.session.commit()
    login(client, "orientando@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/{doc.id}").data.decode()
    assert "Tarefa:" in pagina
    assert f"/cronograma/{tarefa.id}" in pagina
    assert "Texto a revisar em:" in pagina
    assert f"/cronograma/{revisao.id}" in pagina


# --- painel enxuto: próximo à vista, grupo numa linha, encerradas recolhidas ---

import uuid  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from app.models import Marco  # noqa: E402


def _cortar(pagina, inicio, fim_marcador="<details"):
    trecho = pagina[pagina.index(inicio):]
    corte = trecho.find(fim_marcador)
    return (trecho, "") if corte < 0 else (trecho[:corte], trecho[corte:])


def test_proximas_a_vista_e_distantes_recolhidas(client, orientacao, orientando):
    hoje = date.today()
    _marco(orientacao, titulo="Vence logo", data_prevista=hoje + timedelta(days=10))
    _marco(orientacao, titulo="Ja atrasada", data_prevista=hoje - timedelta(days=3))
    _marco(orientacao, titulo="Vence longe", data_prevista=hoje + timedelta(days=120))
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()
    vista, recolhido = _cortar(pagina, "Tarefas a fazer")
    assert "Vence logo" in vista and "Ja atrasada" in vista
    assert "Vence longe" not in vista and "Vence longe" in recolhido
    assert "Ver as demais (1)" in recolhido


def test_tarefa_em_grupo_numa_linha_com_um_link_por_orientando(
    client, orientacao, orientacao2, orientador
):
    gid = uuid.uuid4().hex
    prazo = date.today() + timedelta(days=7)
    m1 = _marco(orientacao, titulo="Fundamentos de Python", grupo_id=gid, data_prevista=prazo)
    m2 = _marco(orientacao2, titulo="Fundamentos de Python", grupo_id=gid, data_prevista=prazo)
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    vista, _ = _cortar(pagina, "Tarefas a fazer")
    assert vista.count("Fundamentos de Python") == 1
    assert f"/cronograma/{m1.id}" in vista and f"/cronograma/{m2.id}" in vista
    assert "Orientando B" in vista and "Orientando D" in vista

    # quem sinalizou sai da linha do grupo (está em outra fila)
    m2.conclusao_sinalizada = True
    m2.status = "em_andamento"
    db.session.commit()
    vista, _ = _cortar(client.get("/dashboard").data.decode(), "Tarefas a fazer")
    assert f"/cronograma/{m2.id}" not in vista and f"/cronograma/{m1.id}" in vista


def test_orientacao_encerrada_fica_recolhida(client, orientacao, orientacao2, orientador):
    orientacao2.status = "concluida"
    db.session.commit()
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    principal = pagina[pagina.index("Minhas orientações"):pagina.index("Orientações encerradas")]
    assert "Segundo Projeto" not in principal
    assert "Projeto de Teste" in principal
    encerradas = pagina[pagina.index("Orientações encerradas (1)"):]
    assert "Segundo Projeto" in encerradas


def test_total_de_pendencias_conta_tudo(app, client, orientacao, orientador):
    from flask_login import login_user

    from app.services import painel

    hoje = date.today()
    _marco(orientacao, titulo="Perto", data_prevista=hoje + timedelta(days=5))
    _marco(orientacao, titulo="Longe", data_prevista=hoje + timedelta(days=200))
    with client.application.test_request_context():
        login_user(orientador)
        pend = painel.pendencias()
    assert len(pend["tarefas_a_fazer"]) == 2
    assert len(pend["linhas_a_fazer"]) == 1 and len(pend["linhas_a_fazer_depois"]) == 1
    assert pend["total"] >= 2
    assert Marco.query.count() == 2
