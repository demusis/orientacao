from datetime import date

from app.extensions import db
from app.models import (
    Ata,
    EventoVinculo,
    LogAuditoria,
    Marco,
    OrientacaoOrientador,
    Usuario,
)

from tests.conftest import _criar_usuario, login


# ---------- Sprint A: tipologia de marcos e eventos do vínculo ----------

def test_marco_criado_com_tipo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Exame de qualificação",
            "tipo": "qualificacao",
            "descricao": "",
            "data_prevista": "2027-03-31",
            "etapa": 30,
        },
    )
    assert Marco.query.one().tipo == "qualificacao"


def test_prorrogacao_altera_prazo_com_historico(client, admin, orientacao):
    orientacao.data_fim_prevista = date(2028, 2, 28)
    db.session.commit()
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={
            "tipo": "prorrogacao",
            "fundamentacao": "Afastamento por licença saúde no semestre anterior.",
            "data_nova": "2028-08-31",
            "texto_novo": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert orientacao.data_fim_prevista == date(2028, 8, 31)
    ev = EventoVinculo.query.one()
    assert ev.data_anterior == date(2028, 2, 28)
    assert ev.registrado_em is not None
    assert LogAuditoria.query.filter_by(acao="evento_vinculo").count() == 1


def test_prorrogacao_para_data_anterior_recusada(client, admin, orientacao):
    orientacao.data_fim_prevista = date(2028, 2, 28)
    db.session.commit()
    login(client, "admin@teste.br")
    resp = client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={
            "tipo": "prorrogacao",
            "fundamentacao": "x",
            "data_nova": "2027-01-01",
            "texto_novo": "",
        },
        follow_redirects=True,
    )
    assert "posterior ao fim vigente".encode() in resp.data
    assert EventoVinculo.query.count() == 0


def test_trancamento_e_destrancamento(client, admin, orientacao):
    login(client, "admin@teste.br")
    client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={"tipo": "trancamento", "fundamentacao": "Solicitação do discente.", "texto_novo": ""},
    )
    assert orientacao.status == "suspensa"
    client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={"tipo": "destrancamento", "fundamentacao": "Retorno.", "texto_novo": ""},
    )
    assert orientacao.status == "ativa"
    assert EventoVinculo.query.count() == 2


def test_mudanca_titulo_preserva_anterior(client, admin, orientacao):
    login(client, "admin@teste.br")
    client.post(
        f"/admin/orientacoes/{orientacao.id}/eventos",
        data={
            "tipo": "mudanca_titulo",
            "fundamentacao": "Redelimitação do objeto após qualificação.",
            "texto_novo": "Novo Título do Projeto",
        },
    )
    assert orientacao.titulo_projeto == "Novo Título do Projeto"
    ev = EventoVinculo.query.one()
    assert ev.texto_anterior == "Projeto de Teste"


def test_eventos_restritos_ao_admin(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    assert (
        client.get(f"/admin/orientacoes/{orientacao.id}/eventos").status_code == 403
    )


# ---------- Sprint C: coorientação ----------

def _designar_coorientador(orientacao, usuario):
    db.session.add(
        OrientacaoOrientador(
            orientacao_id=orientacao.id, usuario_id=usuario.id, funcao="coorientador"
        )
    )
    db.session.commit()


def test_admin_designa_e_remove_coorientador(client, admin, orientacao):
    co = _criar_usuario("Coorientadora", "co@teste.br", "orientador")
    login(client, "admin@teste.br")
    client.post(
        f"/admin/orientacoes/{orientacao.id}/coorientadores",
        data={"usuario_id": co.id},
        follow_redirects=True,
    )
    assert any(
        a.usuario_id == co.id and a.funcao == "coorientador" for a in orientacao.equipe
    )
    assert LogAuditoria.query.filter_by(acao="designacao_coorientador").count() == 1

    client.post(
        f"/admin/orientacoes/{orientacao.id}/coorientadores/{co.id}/remover",
        follow_redirects=True,
    )
    assert all(a.usuario_id != co.id for a in orientacao.equipe)


def test_coorientador_ve_vinculo_e_redige_ata(client, orientacao, orientador):
    co = _criar_usuario("Coorientadora", "co@teste.br", "orientador")
    _designar_coorientador(orientacao, co)

    login(client, "co@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}").status_code == 200
    assert "Projeto de Teste".encode() in client.get("/dashboard").data

    resp = client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={
            "data_reuniao": "2026-07-20",
            "pauta": "Reunião conduzida pela coorientadora",
            "deliberacoes": "Encaminhamentos registrados",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Ata.query.count() == 1


def test_coorientador_nao_finaliza_ata_nem_emite_parecer(client, orientacao, orientador):
    co = _criar_usuario("Coorientadora", "co@teste.br", "orientador")
    _designar_coorientador(orientacao, co)

    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()

    client.post("/auth/logout")
    login(client, "co@teste.br")
    resp = client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    assert resp.status_code == 403
    assert ata.status == "rascunho"
    assert (
        client.get(f"/orientacoes/{orientacao.id}/pareceres/novo").status_code == 403
    )
    assert (
        client.get(f"/orientacoes/{orientacao.id}/cronograma/novo").status_code == 403
    )


def test_coorientador_marca_presenca(client, orientacao, orientador):
    co = _criar_usuario("Coorientadora", "co@teste.br", "orientador")
    _designar_coorientador(orientacao, co)

    login(client, "co@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/presenca/{orientacao.id}/presente"
    )
    assert ata.participacao_de(orientacao.id).presenca == "presente"


# ---------- Sprint E: exportação assinável ----------

def _ata_finalizada(client, orientacao):
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "Pauta X", "deliberacoes": "Del Y"},
    )
    ata = Ata.query.one()
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    return ata


def test_pdf_de_ata_finalizada(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    ata = _ata_finalizada(client, orientacao)
    resp = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")
    assert LogAuditoria.query.filter_by(acao="exportacao_pdf").count() == 1


def test_pdf_de_rascunho_recusado(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    resp = client.get(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf", follow_redirects=True
    )
    assert "Apenas atas finalizadas".encode() in resp.data


def test_pdf_restrito_as_partes(client, orientacao, orientador, intruso):
    login(client, "orientador@teste.br")
    ata = _ata_finalizada(client, orientacao)
    client.post("/auth/logout")
    login(client, "intruso@teste.br")
    assert (
        client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf").status_code
        == 403
    )


def test_verificacao_publica_confere_e_detecta_adulteracao(client, orientacao, orientador):
    from app.services.exportacao import hash_ata

    login(client, "orientador@teste.br")
    ata = _ata_finalizada(client, orientacao)
    h = hash_ata(ata)
    client.post("/auth/logout")

    resp = client.get(f"/verificar/ata/{ata.id}/{h}")
    assert resp.status_code == 200 and "CONFERE".encode() in resp.data

    resp = client.get(f"/verificar/ata/{ata.id}/{'0' * 64}")
    assert "NÃO CONFERE".encode() in resp.data


def test_pdf_de_parecer(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo",
        data={
            "tipo": "andamento",
            "versao_documento_id": 0,
            "conteudo": "Andamento adequado.",
            "resultado": "aprovado",
        },
    )
    from app.models import Parecer

    parecer = Parecer.query.one()
    resp = client.get(f"/orientacoes/{orientacao.id}/pareceres/{parecer.id}/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")
