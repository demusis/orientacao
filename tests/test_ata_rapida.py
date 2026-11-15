"""P-7: ata rápida (reunião já ocorrida) com opção de finalizar no mesmo passo,
marcando os convidados como presentes; recusa data futura."""
from app.extensions import db
from app.models import Ata
from tests.conftest import login


def _post(client, orientacao, *, data="2026-07-10", finalizar=False):
    dados = {
        "data_reuniao": data,
        "pauta": "Alinhamento metodológico.",
        "deliberacoes": "Revisar o capítulo 2 até o fim do mês.",
        "orientacoes": [orientacao.id],
    }
    if finalizar:
        dados["finalizar_agora"] = "y"
    return client.post("/reunioes/atas/nova", data=dados, follow_redirects=True)


def test_ata_rapida_finalizada_fica_imutavel_e_presente(client, orientacao):
    login(client, "orientador@teste.br")
    r = _post(client, orientacao, finalizar=True)
    assert r.status_code == 200
    ata = Ata.query.one()
    assert ata.status == "finalizada"
    assert ata.imutavel
    assert ata.conteudo_congelado is not None
    assert [p.presenca for p in ata.participacoes] == ["presente"]


def test_ata_rapida_sem_finalizar_fica_rascunho(client, orientacao):
    login(client, "orientador@teste.br")
    _post(client, orientacao, finalizar=False)
    ata = Ata.query.one()
    assert ata.status == "rascunho"
    assert [p.presenca for p in ata.participacoes] == ["pendente"]


def test_ata_rapida_recusa_data_futura(client, orientacao):
    login(client, "orientador@teste.br")
    r = _post(client, orientacao, data="2030-01-01", finalizar=True)
    assert r.status_code == 200
    assert Ata.query.count() == 0
    assert db.session.query(Ata).count() == 0


def test_ata_rapida_registra_presentes_e_ausentes(client, orientacao, orientacao2):
    import json

    login(client, "orientador@teste.br")
    r = client.post(
        "/reunioes/atas/nova",
        data={
            "data_reuniao": "2026-07-10",
            "pauta": "Reunião do grupo",
            "deliberacoes": "Encaminhamentos registrados.",
            "orientacoes": [orientacao.id],
            "ausentes": [orientacao2.id],
            "finalizar_agora": "y",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    ata = Ata.query.one()
    assert ata.status == "finalizada"
    assert ata.tipo == "grupo"
    presencas = {p.orientacao_id: p.presenca for p in ata.participacoes}
    assert presencas == {orientacao.id: "presente", orientacao2.id: "ausente"}
    assert all(p.presenca_registrada_em is not None for p in ata.participacoes)

    congelado = json.loads(ata.conteudo_congelado)
    por_id = {p["orientacao_id"]: p["presenca"] for p in congelado["participacoes"]}
    assert por_id == {orientacao.id: "presente", orientacao2.id: "ausente"}
