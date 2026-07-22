"""Competências sobre o vínculo (decisão de 20/07/2026): o orientador altera o
título do projeto; as datas de início e fim são privativas do administrador."""
import json
from datetime import date

from app.extensions import db
from app.models import EventoVinculo, LogAuditoria
from tests.conftest import _criar_usuario, login

# --- título do projeto: orientador ---


def test_orientador_altera_titulo_com_evento_registrado(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/titulo",
        data={
            "titulo_projeto": "Título Revisado",
            "fundamentacao": "Redelimitação do objeto após qualificação.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert orientacao.titulo_projeto == "Título Revisado"

    evento = EventoVinculo.query.filter_by(tipo="mudanca_titulo").one()
    assert evento.texto_anterior == "Projeto de Teste"
    assert evento.texto_novo == "Título Revisado"
    assert evento.registrado_por == orientador.id
    assert evento.fundamentacao  # fundamentação é obrigatória


def test_alteracao_de_titulo_exige_fundamentacao(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/titulo",
        data={"titulo_projeto": "Sem Fundamento", "fundamentacao": ""},
        follow_redirects=True,
    )
    assert orientacao.titulo_projeto == "Projeto de Teste"
    assert EventoVinculo.query.count() == 0


def test_orientando_e_coorientador_nao_alteram_titulo(
    client, orientacao, orientando, orientador
):
    from app.models import OrientacaoOrientador

    co = _criar_usuario("Co X", "co@teste.br", "orientador")
    db.session.add(
        OrientacaoOrientador(
            orientacao_id=orientacao.id, usuario_id=co.id, funcao="coorientador"
        )
    )
    db.session.commit()

    for email in ("orientando@teste.br", "co@teste.br"):
        login(client, email)
        assert (
            client.get(f"/orientacoes/{orientacao.id}/titulo").status_code == 403
        ), email
        client.post("/auth/logout")
    assert orientacao.titulo_projeto == "Projeto de Teste"


def test_titulo_identico_nao_gera_evento(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/titulo",
        data={
            "titulo_projeto": orientacao.titulo_projeto,
            "fundamentacao": "Sem mudança real.",
        },
        follow_redirects=True,
    )
    assert EventoVinculo.query.count() == 0


# --- datas do vínculo: administrador ---


def test_admin_ajusta_datas_com_auditoria(client, admin, orientacao):
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/datas",
        data={
            "data_inicio": "2026-02-01",
            "data_fim_prevista": "2028-02-01",
            "fundamentacao": "Afastamento por licença saúde no semestre anterior.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert orientacao.data_inicio == date(2026, 2, 1)
    assert orientacao.data_fim_prevista == date(2028, 2, 1)
    registro = LogAuditoria.query.filter_by(acao="ajuste_datas_orientacao").one()
    # o motivo é a única coisa que a trilha não guardaria sozinha
    assert "licença saúde" in json.loads(registro.dados_json)["fundamentacao"]


def test_ajuste_de_datas_sem_fundamentacao_e_recusado(client, admin, orientacao):
    """Desde a remoção da prorrogação este é o único caminho para o prazo do
    vínculo; alterá-lo sem motivo registrado deixaria a trilha muda."""
    inicio_original = orientacao.data_inicio
    login(client, "admin@teste.br")
    client.post(
        f"/admin/orientacoes/{orientacao.id}/datas",
        data={"data_inicio": "2026-02-01", "data_fim_prevista": "2028-02-01"},
        follow_redirects=True,
    )
    assert orientacao.data_inicio == inicio_original
    assert LogAuditoria.query.filter_by(acao="ajuste_datas_orientacao").count() == 0


def test_fim_anterior_ao_inicio_e_recusado(client, admin, orientacao):
    inicio_original = orientacao.data_inicio
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/datas",
        data={
            "data_inicio": "2026-02-01",
            "data_fim_prevista": "2025-01-01",
            "fundamentacao": "x",
        },
        follow_redirects=True,
    )
    assert "posterior".encode() in resp.data
    assert orientacao.data_inicio == inicio_original


def test_orientador_nao_ajusta_datas(client, orientacao, orientador):
    inicio_original = orientacao.data_inicio
    login(client, "orientador@teste.br")
    assert (
        client.get(f"/admin/orientacoes/{orientacao.id}/datas").status_code == 403
    )
    client.post(
        f"/admin/orientacoes/{orientacao.id}/datas",
        data={"data_inicio": "2020-01-01", "data_fim_prevista": ""},
    )
    assert orientacao.data_inicio == inicio_original


def test_pagina_do_vinculo_oferece_titulo_conforme_papel(
    client, orientacao, orientador, orientando
):
    login(client, "orientador@teste.br")
    assert b"Alterar t" in client.get(f"/orientacoes/{orientacao.id}").data
    client.post("/auth/logout")

    login(client, "orientando@teste.br")
    assert b"Alterar t" not in client.get(f"/orientacoes/{orientacao.id}").data
