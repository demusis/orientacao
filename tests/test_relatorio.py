"""Lote 5: relatório consolidado do vínculo em PDF."""
from datetime import date, timedelta

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    Documento,
    Marco,
    Parecer,
    VersaoDocumento,
)
from app.services import relatorio
from tests.conftest import login


def _povoar(orientacao, orientador, orientando):
    db.session.add(Marco(
        orientacao_id=orientacao.id, titulo="Qualificação",
        data_prevista=date.today() + timedelta(days=30), etapa=20, tipo="qualificacao",
    ))
    db.session.add(Marco(
        orientacao_id=orientacao.id, titulo="Capítulo atrasado",
        data_prevista=date.today() - timedelta(days=5),
    ))
    ata = Ata(
        orientador_id=orientador.id, data_reuniao=date.today() - timedelta(days=3),
        pauta="Discussão do método", deliberacoes="**Refazer** a amostra",
        redigida_por=orientador.id, status="finalizada",
    )
    db.session.add(ata)
    db.session.flush()
    db.session.add(AtaParticipacao(
        ata_id=ata.id, orientacao_id=orientacao.id, presenca="presente"
    ))
    doc = Documento(
        orientacao_id=orientacao.id, titulo="Projeto de pesquisa",
        criado_por=orientando.id,
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id, numero_versao=1, nome_original="p.pdf",
        nome_fisico=f"{doc.id:032x}.pdf", tamanho_bytes=1024,
        mimetype="application/pdf", enviado_por=orientando.id,
    )
    db.session.add(v)
    db.session.flush()
    db.session.add(Parecer(
        orientacao_id=orientacao.id, versao_documento_id=v.id, tipo="documento",
        conteudo="Aprovado com **ressalvas** na seção 3.",
        resultado="aprovado_com_ressalvas", emitido_por=orientador.id,
    ))
    db.session.commit()


def test_relatorio_gera_pdf(client, orientacao, orientador, orientando):
    _povoar(orientacao, orientador, orientando)
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500


def test_relatorio_de_vinculo_vazio_nao_quebra(client, orientacao):
    """Vínculo recém-criado, sem marco nem ata: as seções dizem 'nenhum', não
    falham."""
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    assert pdf.startswith(b"%PDF")


def test_rota_entrega_pdf_as_partes(client, orientacao, orientador, orientando):
    _povoar(orientacao, orientador, orientando)
    login(client, "orientador@teste.br")
    r = client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF")


def test_orientando_tambem_acessa(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf").status_code == 200


def test_terceiro_nao_acessa(client, orientacao, intruso):
    login(client, "intruso@teste.br")
    assert client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf").status_code == 403


def test_link_na_pagina_do_vinculo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}").data.decode()
    assert "relatorio.pdf" in pagina
