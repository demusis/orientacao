"""Lote 5: relatório consolidado do vínculo em PDF."""
from datetime import UTC, date, datetime, timedelta

from app.extensions import db
from app.models import (
    AnexoVersao,
    Ata,
    AtaParticipacao,
    Documento,
    EventoVinculo,
    Marco,
    Parecer,
    VersaoDocumento,
)
from app.services import relatorio
from tests.conftest import login


def _povoar(orientacao, orientador, orientando):
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação & Banca",
        descricao="Entrega do texto completo <revisado>",
        data_prevista=date.today() + timedelta(days=30),
        etapa=20,
        tipo="qualificacao",
        entrega_esperada="documento",
    )
    m2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Capítulo atrasado",
        data_prevista=date.today() - timedelta(days=5),
        status="em_andamento",
        devolvido_em=datetime.now(UTC),
        nota_devolucao="Ajustar seção 2 & referências",
    )
    db.session.add_all([m1, m2])
    db.session.flush()
    ata_fin = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() - timedelta(days=3),
        pauta="Discussão do método",
        deliberacoes="**Refazer** a amostra",
        redigida_por=orientador.id,
        status="finalizada",
    )
    ata_canc = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() + timedelta(days=2),
        pauta="Encontro extra",
        deliberacoes="",
        redigida_por=orientador.id,
        status="cancelada",
        motivo_cancelamento="Conflito de agenda",
    )
    db.session.add_all([ata_fin, ata_canc])
    db.session.flush()
    db.session.add_all([
        AtaParticipacao(ata_id=ata_fin.id, orientacao_id=orientacao.id, presenca="presente"),
        AtaParticipacao(ata_id=ata_canc.id, orientacao_id=orientacao.id, presenca="pendente"),
    ])
    doc = Documento(
        orientacao_id=orientacao.id,
        marco_id=m1.id,
        titulo="Projeto de pesquisa <v1>",
        criado_por=orientando.id,
    )
    db.session.add(doc)
    db.session.flush()
    v1 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        nome_original="p.pdf",
        nome_fisico=f"{doc.id:032x}.pdf",
        tamanho_bytes=1024,
        mimetype="application/pdf",
        enviado_por=orientando.id,
        comentario="Primeira versão enviada",
    )
    v2 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=2,
        nome_original=None,
        nome_fisico=None,
        tamanho_bytes=None,
        mimetype=None,
        enviado_por=orientador.id,
        eh_devolucao=True,
        comentario="Comentário sem arquivo",
    )
    db.session.add_all([v1, v2])
    db.session.flush()
    db.session.add(
        AnexoVersao(
            versao_id=v1.id,
            nome_original="dados & tabela.csv",
            nome_fisico="b" * 32 + ".csv",
            tamanho_bytes=512,
            mimetype="text/csv",
        )
    )
    db.session.add(
        Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=v1.id,
            tipo="documento",
            conteudo="Aprovado com **ressalvas** na seção 3.",
            resultado="aprovado_com_ressalvas",
            emitido_por=orientador.id,
        )
    )
    db.session.add(
        EventoVinculo(
            orientacao_id=orientacao.id,
            tipo="mudanca_titulo",
            fundamentacao="Adequação ao escopo",
            texto_anterior="Título antigo",
            texto_novo="Projeto atualizado",
            registrado_por=orientador.id,
        )
    )
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
    assert "Extrato completo do orientando (PDF)" in pagina


def test_atalho_extrato_no_painel_e_em_orientandos(
    client, orientacao, orientador, orientando
):
    login(client, "orientador@teste.br")
    painel_html = client.get("/dashboard").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in painel_html
    assert "Extrato PDF" in painel_html

    orientandos_html = client.get("/orientandos/").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in orientandos_html
    assert "Extrato PDF" in orientandos_html

    # orientando com vínculo encerrado também mantém o acesso ao extrato
    orientacao.status = "concluida"
    db.session.commit()
    orientandos_enc = client.get("/orientandos/").data.decode()
    assert f"/orientacoes/{orientacao.id}/relatorio.pdf" in orientandos_enc
    assert "concluida" in orientandos_enc
