"""Integração relacional: ata↔marco e a linha do tempo do vínculo.

As relações entre marco, documento, parecer e ata existiam nos dados mas eram
invisíveis. Estes testes guardam o que passou a ser navegável — e a regra de que
os marcos discutidos congelam com a ata finalizada.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import (
    Ata, AtaParticipacao, Documento, Marco, Parecer, VersaoDocumento,
)
from app.services import linha_tempo

from tests.conftest import login


def _marco(orientacao, titulo="Qualificação", **kw):
    m = Marco(
        orientacao_id=orientacao.id, titulo=titulo,
        data_prevista=date.today() + timedelta(days=10), **kw,
    )
    db.session.add(m)
    db.session.commit()
    return m


def _versao(orientacao, marco=None, titulo="Projeto"):
    doc = Documento(
        orientacao_id=orientacao.id, titulo=titulo,
        criado_por=orientacao.orientando_id,
        marco_id=marco.id if marco else None,
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id, numero_versao=1, nome_original="p.pdf",
        nome_fisico=f"{doc.id:032x}.pdf", tamanho_bytes=1024,
        mimetype="application/pdf", enviado_por=orientacao.orientando_id,
    )
    db.session.add(v)
    db.session.commit()
    return v


# --- ata <-> marco ---


def test_ata_registra_marcos_discutidos(client, orientacao, orientador):
    m1 = _marco(orientacao, "Qualificação")
    m2 = _marco(orientacao, "Coleta")
    login(client, "orientador@teste.br")

    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={
            "data_reuniao": "2026-08-10", "pauta": "p", "deliberacoes": "d",
            "marcos": [m1.id],
        },
    )
    ata = Ata.query.one()
    assert [m.id for m in ata.marcos] == [m1.id]
    # o marco enxerga a reunião de volta — relação navegável dos dois lados
    assert ata in m1.atas
    assert ata not in m2.atas


def test_edicao_de_rascunho_troca_os_marcos(client, orientacao, orientador):
    m1 = _marco(orientacao, "A")
    m2 = _marco(orientacao, "B")
    ata = Ata(
        orientador_id=orientador.id, data_reuniao=date.today(),
        pauta="p", deliberacoes="d", redigida_por=orientador.id, marcos=[m1],
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=ata.id, orientacao_id=orientacao.id))
    db.session.commit()
    login(client, "orientador@teste.br")

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}",
        data={"pauta": "p2", "deliberacoes": "d2", "marcos": [m2.id], "submit": "1"},
    )
    db.session.refresh(ata)
    assert [m.id for m in ata.marcos] == [m2.id]


def test_marcos_congelam_ao_finalizar(client, orientacao, orientador):
    """Ata finalizada é imutável; os marcos discutidos são parte do registro e
    não mudam mais — a tentativa de edição é barrada como qualquer outra."""
    m1 = _marco(orientacao, "A")
    m2 = _marco(orientacao, "B")
    ata = Ata(
        orientador_id=orientador.id, data_reuniao=date.today(),
        pauta="p", deliberacoes="d", redigida_por=orientador.id,
        status="finalizada", marcos=[m1],
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=ata.id, orientacao_id=orientacao.id))
    db.session.commit()
    login(client, "orientador@teste.br")

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}",
        data={"pauta": "x", "deliberacoes": "y", "marcos": [m2.id], "submit": "1"},
    )
    db.session.refresh(ata)
    # nada mudou: nem conteúdo nem marcos
    assert ata.pauta == "p"
    assert [m.id for m in ata.marcos] == [m1.id]


# --- linha do tempo ---


def test_linha_do_tempo_reune_os_quatro_tipos(client, orientacao, orientador, orientando):
    marco = _marco(orientacao, "Qualificação", data_conclusao=date.today())
    _versao(orientacao, marco=marco)
    ata = Ata(
        orientador_id=orientador.id, data_reuniao=date.today() - timedelta(days=2),
        pauta="p", deliberacoes="d", redigida_por=orientador.id, marcos=[marco],
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=ata.id, orientacao_id=orientacao.id))
    db.session.add(Parecer(
        orientacao_id=orientacao.id, tipo="andamento", conteudo="ok",
        resultado="aprovado", emitido_por=orientador.id,
    ))
    db.session.commit()

    tipos = {e["tipo"] for e in linha_tempo.eventos(orientacao)}
    assert {"marco_previsto", "marco_concluido", "entrega", "parecer", "reuniao"} <= tipos


def test_linha_do_tempo_ordena_do_recente_ao_antigo(client, orientacao):
    db.session.add_all([
        Marco(orientacao_id=orientacao.id, titulo="Velho", data_prevista=date(2026, 1, 1)),
        Marco(orientacao_id=orientacao.id, titulo="Novo", data_prevista=date(2026, 12, 1)),
    ])
    db.session.commit()
    eventos = linha_tempo.eventos(orientacao)
    datas = [e["quando"] for e in eventos]
    assert datas == sorted(datas, reverse=True)


def test_entrega_na_linha_aponta_seu_marco(client, orientacao):
    marco = _marco(orientacao, "Qualificação")
    _versao(orientacao, marco=marco, titulo="Projeto")
    entrega = next(
        e for e in linha_tempo.eventos(orientacao) if e["tipo"] == "entrega"
    )
    assert "Qualificação" in entrega["relacionado"]


def test_rota_da_linha_renderiza_e_filtra(client, orientacao, orientador):
    _marco(orientacao, "Qualificação")
    login(client, "orientador@teste.br")

    tudo = client.get(f"/orientacoes/{orientacao.id}/linha-do-tempo")
    assert tudo.status_code == 200
    assert "Qualificação" in tudo.data.decode()

    # filtro por tipo que não tem eventos: página válida, sem o marco
    so_reunioes = client.get(
        f"/orientacoes/{orientacao.id}/linha-do-tempo?tipo=reuniao"
    ).data.decode()
    assert "Qualificação" not in so_reunioes


def test_linha_restrita_as_partes(client, orientacao, intruso):
    login(client, "intruso@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/linha-do-tempo").status_code == 403


def test_marco_mostra_ligacoes_no_cronograma(client, orientacao, orientador):
    marco = _marco(orientacao, "Qualificação")
    _versao(orientacao, marco=marco, titulo="Projeto entregue")
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/", follow_redirects=True
    ).data.decode()
    assert "entrega: Projeto entregue" in pagina
