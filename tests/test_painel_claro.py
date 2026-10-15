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
