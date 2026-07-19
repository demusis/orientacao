from app.models import Ata, LogAuditoria, Parecer

from tests.conftest import login


def _criar_ata(client, orientacao):
    return client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={
            "data_reuniao": "2026-07-10",
            "pauta": "Discussão do capítulo 2",
            "deliberacoes": "Revisar metodologia até a próxima reunião",
        },
        follow_redirects=True,
    )


def test_orientador_cria_e_finaliza_ata(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    _criar_ata(client, orientacao)
    ata = Ata.query.one()
    assert ata.status == "rascunho"

    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    assert ata.status == "finalizada"
    assert ata.finalizada_em is not None
    assert LogAuditoria.query.filter_by(acao="finalizacao_ata").count() == 1


def test_ata_finalizada_e_imutavel_e_tentativa_e_auditada(app, orientacao, orientador):
    from datetime import date

    from app.extensions import db
    from app.services.atas import AtaImutavel, atualizar_ata, finalizar_ata

    from app.models import AtaParticipacao

    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=date(2026, 7, 10),
        pauta="Pauta",
        deliberacoes="Deliberações",
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(ata)
    db.session.commit()
    finalizar_ata(ata)
    db.session.commit()

    try:
        atualizar_ata(ata, pauta="X", deliberacoes="Y")
        assert False, "Deveria ter levantado AtaImutavel"
    except AtaImutavel:
        db.session.commit()
    assert ata.pauta == "Pauta"
    assert (
        LogAuditoria.query.filter_by(acao="tentativa_edicao_ata_finalizada").count() == 1
    )


def test_emissao_de_parecer_auditada(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo",
        data={
            "tipo": "andamento",
            "versao_documento_id": 0,
            "conteudo": "Progresso adequado ao cronograma.",
            "resultado": "aprovado",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Parecer.query.count() == 1
    assert LogAuditoria.query.filter_by(acao="emissao_parecer").count() == 1
