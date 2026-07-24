"""Cronograma-padrão por modalidade (P-2): semeadura de marcos típicos com data
sugerida a partir do início, sem duplicar e restrita ao orientador."""
from datetime import date

from app.extensions import db
from app.models import Marco
from app.services.cronogramas import _add_meses, semear_cronograma
from tests.conftest import login


def test_add_meses_apara_o_dia_no_fim_do_mes():
    # 31 de janeiro + 1 mês recua para o último dia de fevereiro
    assert _add_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    # soma que cruza o ano
    assert _add_meses(date(2026, 1, 5), 14) == date(2027, 3, 5)


def test_semear_cronograma_mestrado(app, orientacao):
    # a fixture orientacao é mestrado, início 2026-01-05
    criados = semear_cronograma(orientacao)
    db.session.commit()
    assert len(criados) == 4
    por_tipo = {m.tipo: m for m in criados}
    assert set(por_tipo) == {"projeto", "comite_etica", "qualificacao", "defesa"}
    # datas derivadas dos offsets do modelo (mês a partir de data_inicio)
    assert por_tipo["projeto"].data_prevista == date(2026, 4, 5)      # +3
    assert por_tipo["qualificacao"].data_prevista == date(2027, 3, 5)  # +14
    assert por_tipo["defesa"].data_prevista == date(2027, 11, 5)       # +22


def test_rota_semeia_e_nao_duplica(client, orientacao):
    login(client, "orientador@teste.br")
    url = f"/orientacoes/{orientacao.id}/cronograma/padrao"

    r1 = client.post(url, follow_redirects=True)
    assert r1.status_code == 200
    assert Marco.query.filter_by(orientacao_id=orientacao.id).count() == 4

    # segunda tentativa: cronograma já não está vazio → recusa sem duplicar
    r2 = client.post(url, follow_redirects=True)
    assert r2.status_code == 200
    assert Marco.query.filter_by(orientacao_id=orientacao.id).count() == 4


def test_orientando_nao_pode_semear(client, orientacao):
    login(client, "orientando@teste.br")
    r = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/padrao", follow_redirects=False
    )
    assert r.status_code == 403
    assert Marco.query.filter_by(orientacao_id=orientacao.id).count() == 0
