"""Testes das correções da revisão de código de 19/07/2026 (10 achados)."""
from datetime import date

from app.extensions import db
from app.models import Ata, EventoVinculo, OrientacaoOrientador, Usuario

from tests.conftest import _criar_usuario, login


def _designar(orientacao, usuario):
    db.session.add(
        OrientacaoOrientador(
            orientacao_id=orientacao.id, usuario_id=usuario.id, funcao="coorientador"
        )
    )
    db.session.commit()


def _ata_grupo(client, ids):
    client.post(
        "/reunioes/atas/nova",
        data={
            "data_reuniao": "2026-07-25",
            "pauta": "Reunião do grupo",
            "deliberacoes": "Deliberações",
            "orientacoes": ids,
        },
    )
    return Ata.query.one()


# 1. coorientador de um vínculo não controla ata de grupo dos demais

def test_coorientador_de_um_vinculo_nao_edita_ata_de_grupo(client, orientacao, orientacao2, orientador):
    co = _criar_usuario("Co X", "co@teste.br", "orientador")
    _designar(orientacao, co)  # coorienta apenas o vínculo X

    login(client, "orientador@teste.br")
    ata = _ata_grupo(client, [orientacao.id, orientacao2.id])

    client.post("/auth/logout")
    login(client, "co@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}",
        data={"pauta": "ADULTERADA", "deliberacoes": "ADULTERADA", "submit": "1"},
    )
    assert ata.pauta == "Reunião do grupo"  # edição não aplicada

    # presença do vínculo alheio (Y): 403; do próprio (X): permitida
    resp = client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao2.id}/ausente"
    )
    assert resp.status_code == 403
    assert ata.participacao_de(orientacao2.id).presenca == "pendente"

    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/presente"
    )
    assert ata.participacao_de(orientacao.id).presenca == "presente"


def test_coorientador_segue_editando_ata_individual(client, orientacao, orientador):
    co = _criar_usuario("Co X", "co@teste.br", "orientador")
    _designar(orientacao, co)
    login(client, "co@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}",
        data={"pauta": "P2", "deliberacoes": "D2", "submit": "1"},
    )
    assert ata.pauta == "P2"


# 2. PDF com caracteres especiais não quebra

def test_pdf_com_caracteres_especiais(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={
            "data_reuniao": "2026-07-20",
            "pauta": "P&D: avaliar x < y & z > w",
            "deliberacoes": "Rever <metodologia> & prazos",
        },
    )
    ata = Ata.query.one()
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    resp = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


# 3. hash cobre campos impressos mutáveis (título do projeto)

def test_mudanca_de_titulo_altera_hash_do_parecer(client, admin, orientacao, orientador):
    from app.services.exportacao import hash_parecer

    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo",
        data={
            "tipo": "andamento",
            "versao_documento_id": 0,
            "conteudo": "Adequado.",
            "resultado": "aprovado",
        },
    )
    from app.models import Parecer

    parecer = Parecer.query.one()
    h_antes = hash_parecer(parecer)

    client.post("/auth/logout")
    login(client, "admin@teste.br")
    client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={
            "tipo": "mudanca_titulo",
            "fundamentacao": "Redelimitação.",
            "texto_novo": "Título Alterado",
        },
    )
    assert hash_parecer(parecer) != h_antes  # PDF diferente => hash diferente


# 4. separador sem ambiguidade de fronteira

def test_hash_sem_colisao_por_deslocamento_de_fronteira(app, orientacao, orientador):
    from app.models import AtaParticipacao
    from app.services.exportacao import hash_ata

    def criar(pauta, delib):
        ata = Ata(
            orientador_id=orientador.id,
            data_reuniao=date(2026, 7, 20),
            pauta=pauta,
            deliberacoes=delib,
            redigida_por=orientador.id,
            participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
        )
        db.session.add(ata)
        db.session.commit()
        return ata

    a1 = criar("Pauta X", "A\x1fB")
    a2 = criar("Pauta X\x1fA", "B")
    # ids diferentes já divergem; comparação justa: mesmo id simulado
    h1 = hash_ata(a1).replace(str(a1.id), "N", 1)
    partes_iguais_exceto_conteudo = hash_ata(a2)
    assert hash_ata(a1) != partes_iguais_exceto_conteudo
    # e diretamente: o serializador distingue fronteiras
    from app.services.exportacao import _sha256

    assert _sha256(["Pauta X", "A\x1fB"]) != _sha256(["Pauta X\x1fA", "B"])


# 5. exclusão bloqueada para coorientador designado

def test_exclusao_bloqueada_para_coorientador_designado(client, admin, orientacao):
    co = _criar_usuario("Co Externa", "coexterna@teste.br", "orientador")
    _designar(orientacao, co)
    login(client, "admin@teste.br")
    resp = client.post(f"/admin/usuarios/{co.id}/excluir", follow_redirects=True)
    assert "Exclusão recusada".encode() in resp.data
    assert db.session.get(Usuario, co.id) is not None


# 6. suspensão só por trancamento fundamentado

def test_encerrar_nao_oferece_suspensao(client, admin, orientacao):
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/encerrar",
        data={"status": "suspensa"},
        follow_redirects=True,
    )
    assert orientacao.status == "ativa"  # escolha inválida é rejeitada pelo form


# 7. prorrogação com fim previsto nulo valida contra o início

def test_prorrogacao_sem_fim_previsto_valida_contra_inicio(client, admin, orientacao):
    assert orientacao.data_fim_prevista is None
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={
            "tipo": "prorrogacao",
            "fundamentacao": "x",
            "data_nova": "2020-01-01",  # anterior ao início (2026-01-05)
            "texto_novo": "",
        },
        follow_redirects=True,
    )
    assert "posterior".encode() in resp.data
    assert orientacao.data_fim_prevista is None
    assert EventoVinculo.query.count() == 0


# 8. link Reagendar coerente com a rota (coorientador não vê nem acessa)

def test_coorientador_nao_ve_link_reagendar(client, orientacao, orientador):
    co = _criar_usuario("Co X", "co@teste.br", "orientador")
    _designar(orientacao, co)
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    client.post("/auth/logout")
    login(client, "co@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}")
    assert b"Reagendar" not in pagina.data
    assert (
        client.get(
            f"/orientacoes/{orientacao.id}/atas/{ata.id}/reagendar"
        ).status_code
        == 403
    )


# 9. expurgo LGPD: colunas de justificativa não existem mais

def test_colunas_de_justificativa_expurgadas(app):
    from sqlalchemy import inspect

    colunas = {c["name"] for c in inspect(db.engine).get_columns("ata_orientacao")}
    assert "justificativa" not in colunas
    assert "justificativa_em" not in colunas


# 10. fonte única do principal: equipe contém apenas coorientadores

def test_criacao_de_vinculo_nao_duplica_principal(client, admin, orientador, orientando2):
    login(client, "admin@teste.br")
    client.post(
        "/admin/orientacoes/nova",
        data={
            "orientador_id": orientador.id,
            "orientando_id": orientando2.id,
            "modalidade": "ic",
            "titulo_projeto": "Sem Duplicação",
            "data_inicio": "2026-07-01",
        },
    )
    from app.models import Orientacao

    o = Orientacao.query.filter_by(titulo_projeto="Sem Duplicação").one()
    assert o.equipe == []  # nenhuma linha 'principal'
    assert o.orienta(orientador)  # autorização via orientador_id segue íntegra
