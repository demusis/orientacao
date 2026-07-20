"""Testes das correções das revisões de código de 19–20/07/2026."""
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


# 3. conteúdo congelado na emissão: alteração externa posterior não invalida
# o documento já assinável (PDF e hash derivam do snapshot)

def test_mudanca_de_titulo_nao_invalida_parecer_emitido(client, admin, orientacao, orientador):
    import json

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
    assert parecer.conteudo_congelado  # congelado na emissão
    h_antes = hash_parecer(parecer)
    titulo_original = orientacao.titulo_projeto

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
    assert orientacao.titulo_projeto == "Título Alterado"
    # hash estável: o PDF já emitido continua verificável
    assert hash_parecer(parecer) == h_antes
    # e o PDF continua imprimindo o título vigente na emissão
    assert json.loads(parecer.conteudo_congelado)["projeto"] == titulo_original
    resp = client.get(
        f"/verificar/parecer/{parecer.id}/{h_antes}", follow_redirects=True
    )
    assert resp.status_code == 200


def test_finalizacao_congela_conteudo_da_ata(client, orientacao, orientador):
    from app.services.exportacao import hash_ata

    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    assert ata.conteudo_congelado is None  # rascunho ainda não congelado
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    assert ata.conteudo_congelado
    h = hash_ata(ata)

    # correção de nome posterior à finalização não invalida o documento
    orientador.nome = "Orientador A Corrigido"
    db.session.commit()
    assert hash_ata(ata) == h
    resp = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


def test_botao_link_tem_cor_propria(app):
    """Regressão visual: `button.link` sem `color` herda o branco da regra
    genérica de `button` e some sobre o fundo claro das tabelas (a coluna de
    ações aparecia vazia embora o botão estivesse no HTML)."""
    import pathlib
    import re

    css = pathlib.Path(app.root_path, "static", "style.css").read_text(encoding="utf-8")
    regra = re.search(r"button\.link\s*\{([^}]*)\}", css)
    assert regra, "regra button.link ausente"
    assert "color:" in regra.group(1), "button.link precisa declarar color"


# 4. serialização canônica sem ambiguidade de fronteira entre campos

def test_hash_sem_colisao_por_deslocamento_de_fronteira(app):
    from app.services.exportacao import _sha256

    assert _sha256(["Pauta X", "A\x1fB"]) != _sha256(["Pauta X\x1fA", "B"])
    assert _sha256({"a": "x|y", "b": ""}) != _sha256({"a": "x", "b": "y"})


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
    client.post(
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
