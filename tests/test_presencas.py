from app.models import Ata, LogAuditoria, Reagendamento

from tests.conftest import login


def _criar_ata_grupo(client, orientacoes_ids):
    return client.post(
        "/reunioes/atas/nova",
        data={
            "data_reuniao": "2026-07-25",
            "hora_reuniao": "14:00",
            "pauta": "Reunião do grupo",
            "deliberacoes": "Deliberações iniciais",
            "orientacoes": orientacoes_ids,
        },
        follow_redirects=True,
    )


def test_reagendamento_registra_historico_com_data_e_hora(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()
    assert ata.hora_reuniao.strftime("%H:%M") == "14:00"

    resp = client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/reagendar",
        data={
            "data_reuniao": "2026-08-01",
            "hora_reuniao": "09:30",
            "motivo": "Conflito com banca de defesa",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert str(ata.data_reuniao) == "2026-08-01"
    assert ata.hora_reuniao.strftime("%H:%M") == "09:30"

    reg = Reagendamento.query.one()
    assert str(reg.data_anterior) == "2026-07-25"
    assert str(reg.data_nova) == "2026-08-01"
    assert reg.motivo == "Conflito com banca de defesa"
    assert reg.registrado_em is not None  # carimbo de data/hora da ação
    assert LogAuditoria.query.filter_by(acao="reagendamento_reuniao").count() == 1


def test_ata_finalizada_nao_reagenda(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/reagendar",
        data={"data_reuniao": "2026-09-01", "motivo": ""},
    )
    assert str(ata.data_reuniao) == "2026-07-25"
    assert Reagendamento.query.count() == 0
    assert (
        LogAuditoria.query.filter_by(
            acao="tentativa_reagendamento_ata_finalizada"
        ).count()
        == 1
    )


def test_orientador_assinala_presenca_e_ausencia(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/presente"
    )
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao2.id}/ausente"
    )
    p1 = ata.participacao_de(orientacao.id)
    p2 = ata.participacao_de(orientacao2.id)
    assert p1.presenca == "presente" and p2.presenca == "ausente"
    assert p1.presenca_registrada_em is not None  # data/hora da ação
    assert p1.presenca_registrada_por == orientacao.orientador_id
    assert LogAuditoria.query.filter_by(acao="registro_presenca").count() == 2


def test_orientando_nao_assinala_presenca(client, orientacao, orientacao2, orientador, orientando):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/presente"
    )
    assert resp.status_code == 403
    assert ata.participacao_de(orientacao.id).presenca == "pendente"


def test_orientando_ausente_justifica_facultativamente(client, orientacao, orientacao2, orientador, orientando):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/ausente"
    )

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/justificativa",
        data={"justificativa": "Consulta médica agendada previamente."},
        follow_redirects=True,
    )
    p = ata.participacao_de(orientacao.id)
    assert p.justificativa == "Consulta médica agendada previamente."
    assert p.justificativa_em is not None  # data/hora da ação
    assert LogAuditoria.query.filter_by(acao="justificativa_ausencia").count() == 1


def test_justificativa_exige_ausencia_registrada(client, orientacao, orientacao2, orientador, orientando):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/justificativa",
        data={"justificativa": "Tentativa sem ausência."},
    )
    assert ata.participacao_de(orientacao.id).justificativa is None


def test_presenca_bloqueada_apos_finalizacao(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    _criar_ata_grupo(client, [orientacao.id, orientacao2.id])
    ata = Ata.query.one()
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/presente"
    )
    assert ata.participacao_de(orientacao.id).presenca == "pendente"
    assert (
        LogAuditoria.query.filter_by(acao="tentativa_presenca_ata_finalizada").count()
        == 1
    )
