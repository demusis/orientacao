"""Testes da análise e pontuação de risco de descumprimento de prazos."""
import base64
import re
import zlib
from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import Ata, AtaParticipacao, Marco
from app.services import painel
from app.services.tempo import hoje_local
from tests.conftest import login


def test_risco_baixo_cronograma_em_dia(app, orientacao):
    """Vínculo com cronograma em dia e marcos sem atraso deve ter risco baixo (<25)."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=60)
    orientacao.data_fim_prevista = hoje + timedelta(days=300)

    # 2 marcos: 1 concluído antes do prazo, 1 futuro
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Levantamento inicial",
        data_prevista=hoje - timedelta(days=10),
        data_conclusao=hoje - timedelta(days=15),
        status="concluido",
    )
    m2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Redação inicial",
        data_prevista=hoje + timedelta(days=90),
        status="pendente",
    )
    db.session.add_all([m1, m2])
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["nivel"] == "baixo"
    assert resultado["pontuacao"] < 25
    assert resultado["pts_atraso"] == 0
    assert resultado["cor_badge"] == "baixo"
    assert resultado["rotulo"] == "Baixo"
    assert any("em dia" in f.lower() or "sem atrasos" in f.lower() for f in resultado["fatores"])


def test_risco_alto_com_atrasos_defasagem_e_faltas(app, orientacao, orientador):
    """Vínculo com atrasos múltiplos, defasagem entre tempo e entregas, e faltas em atas."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=250)
    orientacao.data_fim_prevista = hoje + timedelta(days=50)

    # 5 marcos no total: 1 concluído + 4 em aberto (2 vencidos + 2 futuros)
    m_concluido = Marco(
        orientacao_id=orientacao.id,
        titulo="Planejamento inicial",
        data_prevista=hoje - timedelta(days=200),
        data_conclusao=hoje - timedelta(days=205),
        status="concluido",
    )
    m_vencido1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisão bibliográfica",
        data_prevista=hoje - timedelta(days=30),
        status="pendente",
    )
    m_vencido2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Coleta de dados preliminar",
        data_prevista=hoje - timedelta(days=10),
        status="pendente",
    )
    m_futuro1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Análise preliminar",
        data_prevista=hoje + timedelta(days=15),
        status="pendente",
    )
    m_futuro2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Escrita do manuscrito",
        data_prevista=hoje + timedelta(days=40),
        status="pendente",
    )
    db.session.add_all([m_concluido, m_vencido1, m_vencido2, m_futuro1, m_futuro2])

    # 4 atas finalizadas: 3 ausente, 1 presente
    for i in range(4):
        presenca = "ausente" if i < 3 else "presente"
        ata = Ata(
            tipo="individual",
            orientador_id=orientador.id,
            data_reuniao=hoje - timedelta(days=80 - i * 15),
            pauta=f"Reunião de acompanhamento {i + 1}",
            deliberacoes=f"Deliberações da reunião {i + 1}",
            redigida_por=orientador.id,
            status="finalizada",
            participacoes=[
                AtaParticipacao(orientacao_id=orientacao.id, presenca=presenca)
            ],
        )
        db.session.add(ata)

    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pontuacao"] >= 50
    assert resultado["nivel"] in ("alto", "critico")
    assert resultado["pts_atraso"] > 0
    assert resultado["pts_ritmo"] > 0
    assert resultado["pts_assiduidade"] >= 10

    fatores_str = " ".join(resultado["fatores"])
    assert "em atraso" in fatores_str
    assert "Revisão bibliográfica" in fatores_str
    assert "Descompasso" in fatores_str
    assert "Ausência em reuniões" in fatores_str


def test_marco_critico_vencido_eleva_para_critico(app, orientacao):
    """Marco crítico (ex.: qualificação) vencido eleva automaticamente a pontuação para crítico (>=75)."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=30)
    orientacao.data_fim_prevista = hoje + timedelta(days=330)

    marco_critico = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação de Mestrado",
        tipo="qualificacao",
        data_prevista=hoje - timedelta(days=5),
        status="pendente",
    )
    db.session.add(marco_critico)
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pts_criticos"] >= 15
    assert resultado["pontuacao"] >= 75
    assert resultado["nivel"] == "critico"
    assert resultado["cor_badge"] == "alto"
    assert resultado["rotulo"] == "Crítico"
    assert any("Marco crítico vencido" in f for f in resultado["fatores"])


def test_prazo_final_estourado_com_marcos_abertos_eleva_para_critico(app, orientacao):
    """Data final prevista já expirada com marcos em aberto eleva o risco para crítico."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=360)
    orientacao.data_fim_prevista = hoje - timedelta(days=5)

    marco_aberto = Marco(
        orientacao_id=orientacao.id,
        titulo="Depósito da dissertação",
        data_prevista=hoje + timedelta(days=10),
        status="pendente",
    )
    db.session.add(marco_aberto)
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pontuacao"] >= 75
    assert resultado["nivel"] == "critico"
    assert any("Prazo final previsto vencido" in f for f in resultado["fatores"])


def test_marco_critico_proximo_e_tarefa_devolvida(app, orientacao):
    """Marco crítico a vencer em menos de 30 dias (5 pts) + tarefa devolvida aguardando revisão (5 pts)."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=60)
    orientacao.data_fim_prevista = hoje + timedelta(days=300)

    m_defesa = Marco(
        orientacao_id=orientacao.id,
        titulo="Defesa de Dissertação",
        tipo="defesa",
        data_prevista=hoje + timedelta(days=10),
        status="pendente",
    )
    m_devolvido = Marco(
        orientacao_id=orientacao.id,
        titulo="Artigo para revisão",
        tipo="outro",
        data_prevista=hoje + timedelta(days=40),
        status="pendente",
        devolvido_em=datetime.now(UTC),
    )
    db.session.add_all([m_defesa, m_devolvido])
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pts_criticos"] == 10
    assert any("Marco crítico próximo" in f for f in resultado["fatores"])
    assert any("devolvida(s)" in f for f in resultado["fatores"])


def test_vinculo_concluido_zera_risco(app, orientacao):
    """Vínculo com status 'concluida' sempre zera a pontuação e indicadores de risco."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=300)
    orientacao.data_fim_prevista = hoje - timedelta(days=20)
    orientacao.status = "concluida"

    marco_atrasado = Marco(
        orientacao_id=orientacao.id,
        titulo="Entrega de versão final",
        data_prevista=hoje - timedelta(days=50),
        status="pendente",
    )
    db.session.add(marco_atrasado)
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pontuacao"] == 0
    assert resultado["nivel"] == "baixo"
    assert resultado["cor_badge"] == "baixo"
    assert resultado["rotulo"] == "Baixo"
    assert resultado["fatores"] == ["Vínculo concluído."]


def test_pdf_e_pagina_do_vinculo_destacam_analise_de_risco(client, orientacao, orientador):
    """Verifica a presença da análise de risco na página HTML e no relatório em PDF do vínculo."""
    hoje = hoje_local()
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisão bibliográfica",
        data_prevista=hoje - timedelta(days=30),
        status="pendente",
    )
    db.session.add(m)
    db.session.commit()

    login(client, orientador.email)
    r = painel.analisar_risco_prazos(orientacao)

    # 1. Página HTML do vínculo
    resp_html = client.get(f"/orientacoes/{orientacao.id}")
    assert resp_html.status_code == 200
    html = resp_html.data.decode()
    assert "Risco de descumprimento de prazos" in html
    assert f"{r['pontuacao']}/100" in html
    assert r["rotulo"] in html
    assert any(f in html for f in r["fatores"])

    # 2. Relatório PDF consolidado
    resp_pdf = client.get(f"/orientacoes/{orientacao.id}/relatorio.pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.content_type == "application/pdf"

    pdf_bytes = resp_pdf.data
    conteudo_pdf = pdf_bytes.decode("latin1", errors="ignore")
    for match in re.finditer(rb"stream\r?\n(.*?)(?:~>|\r?\n)?endstream", pdf_bytes, re.DOTALL):
        raw = match.group(1).strip()
        try:
            conteudo_pdf += zlib.decompress(raw).decode("latin1", errors="ignore")
        except Exception:
            pass
        try:
            raw_a85 = raw if raw.endswith(b"~>") else raw + b"~>"
            conteudo_pdf += zlib.decompress(base64.a85decode(raw_a85, adobe=True)).decode(
                "latin1", errors="ignore"
            )
        except Exception:
            pass

    # Converte eventuais sequências de escape octais típicas de PDF em caracteres
    conteudo_legivel = re.sub(
        r"\\([0-7]{1,3})",
        lambda m_oct: chr(int(m_oct.group(1), 8)),
        conteudo_pdf,
    )

    assert f"{r['pontuacao']}/100" in conteudo_legivel
    assert (
        "Análise de risco dos prazos" in conteudo_legivel
        or "Análise de risco dos prazos" in conteudo_pdf
        or "risco dos prazos" in conteudo_legivel
    )

    # Verifica que o bloco de análise de risco vem antes da tabela de cronograma
    idx_risco = conteudo_legivel.find("Análise de risco dos prazos")
    if idx_risco == -1:
        idx_risco = conteudo_legivel.find("risco dos prazos")
    idx_cronograma = conteudo_legivel.find("Cronograma e entregas por tarefa")
    if idx_cronograma == -1:
        idx_cronograma = conteudo_legivel.find("Cronograma")

    assert idx_risco != -1
    if idx_cronograma != -1:
        assert idx_risco < idx_cronograma
