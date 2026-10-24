"""Exclusão da tarefa individual criada por engano — só a limpa."""
from datetime import date

from app.extensions import db
from app.models import Documento, LogAuditoria, Marco
from tests.conftest import login


def _marco(orientacao, **kw):
    m = Marco(orientacao_id=orientacao.id, titulo="Duplicada",
              data_prevista=date(2026, 12, 1), **kw)
    db.session.add(m)
    db.session.commit()
    return m


def _url(orientacao, marco):
    return f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/excluir"


def test_orientador_exclui_tarefa_limpa(client, orientacao, orientador):
    marco = _marco(orientacao)
    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}").data.decode()
    assert "Excluir tarefa" in pagina
    assert "Não há como desfazer" in client.get(_url(orientacao, marco)).data.decode()
    resp = client.post(_url(orientacao, marco), follow_redirects=True)
    assert "excluída" in resp.data.decode()
    assert Marco.query.count() == 0
    assert LogAuditoria.query.filter_by(acao="exclusao_marco").count() == 1


def test_tarefa_com_historico_e_preservada(client, orientacao, orientador):
    marco = _marco(orientacao)
    db.session.add(Documento(orientacao_id=orientacao.id, marco_id=marco.id,
                             titulo="Entrega", criado_por=orientacao.orientando_id))
    db.session.commit()
    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}").data.decode()
    assert "Excluir tarefa" not in pagina
    resp = client.post(_url(orientacao, marco), follow_redirects=True)
    assert "não pode ser excluída" in resp.data.decode()
    assert Marco.query.count() == 1
    assert LogAuditoria.query.filter_by(acao="exclusao_tarefa_recusada").count() == 1


def test_sinalizada_e_preservada(client, orientacao, orientador):
    marco = _marco(orientacao, conclusao_sinalizada=True, status="em_andamento")
    login(client, "orientador@teste.br")
    client.post(_url(orientacao, marco))
    assert Marco.query.count() == 1


def test_orientando_nao_exclui(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    assert client.post(_url(orientacao, marco)).status_code == 403
    assert Marco.query.count() == 1


def test_exclui_ligacao_com_material(client, orientacao, orientador):
    from app.models import Material, material_marco

    marco = _marco(orientacao)
    mat = Material(titulo="M", nome_original="m.pdf", nome_fisico="a" * 32 + ".pdf",
                   tamanho_bytes=1, mimetype="application/pdf",
                   enviado_por=orientacao.orientador_id, marcos=[marco])
    db.session.add(mat)
    db.session.commit()
    login(client, "orientador@teste.br")
    client.post(_url(orientacao, marco))
    assert Marco.query.count() == 0
    assert db.session.execute(material_marco.select()).fetchall() == []
    assert Material.query.count() == 1
