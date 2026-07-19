from datetime import date, timedelta

from app.extensions import db
from app.models import Marco

from tests.conftest import login


def _criar_marco(orientacao, dias=30):
    marco = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação",
        data_prevista=date.today() + timedelta(days=dias),
    )
    db.session.add(marco)
    db.session.commit()
    return marco


def test_orientador_cria_marco(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Revisão bibliográfica",
            "descricao": "",
            "data_prevista": "2026-09-30",
            "ordem": 1,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Marco.query.count() == 1


def test_fluxo_sinalizacao_e_confirmacao(client, orientacao, orientador, orientando):
    marco = _criar_marco(orientacao)

    login(client, "orientando@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/sinalizar")
    assert marco.conclusao_sinalizada is True
    assert marco.status == "em_andamento"

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/confirmar")
    assert marco.status == "concluido"
    assert marco.data_conclusao == date.today()


def test_orientando_nao_confirma_conclusao(client, orientacao, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/confirmar"
    )
    assert resp.status_code == 403
    assert marco.status == "pendente"


def test_marco_atrasado_computado_na_leitura(app, orientacao):
    marco = _criar_marco(orientacao, dias=-5)
    assert marco.atrasado is True
    marco.status = "concluido"
    assert marco.atrasado is False
