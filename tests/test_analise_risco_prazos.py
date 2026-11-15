"""Testes da análise e pontuação de risco de descumprimento de prazos."""
import base64
import json
import re
import zlib
from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoRisco,
    Documento,
    Marco,
    Parecer,
    VersaoDocumento,
)
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
    assert "em atraso" in fatores_str or "atraso" in fatores_str.lower()
    assert "Revisão bibliográfica" in fatores_str
    assert "Descompasso" in fatores_str or "ritmo" in fatores_str.lower() or "spi" in fatores_str.lower()
    assert "Ausência em reuniões" in fatores_str or "ausência" in fatores_str.lower() or "falta" in fatores_str.lower()


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
    assert any("Marco crítico vencido" in f or "crítico vencido" in f.lower() for f in resultado["fatores"])


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
    assert any("Prazo final previsto vencido" in f or "prazo final" in f.lower() for f in resultado["fatores"])


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
    assert resultado["pts_criticos"] >= 10
    assert any("Marco crítico próximo" in f or "crítico próximo" in f.lower() for f in resultado["fatores"])
    assert any("devolvida(s)" in f or "devolvida" in f.lower() for f in resultado["fatores"])


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


# ==============================================================================
# NOVOS TESTES: MODELO MULTIDIMENSIONAL PARAMETRIZÁVEL (Earned Schedule + EWS)
# ==============================================================================


def test_earned_schedule_metricas_ponderadas_e_pesos_padrao(app, orientacao):
    """Métricas de Earned Schedule com pesos diferenciados por marco e pesos padrão do modelo."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=90)
    orientacao.data_fim_prevista = hoje + timedelta(days=180)

    # Marcos com pesos diferentes:
    # 1. m_qualif: tipo qualificacao -> peso 3.0 (concluído)
    # 2. m_artigo: tipo publicacao -> peso 2.0 (pendente)
    # 3. m_outro: tipo outro -> peso 1.0 (pendente)
    m_qualif = Marco(
        orientacao_id=orientacao.id,
        titulo="Exame de Qualificação",
        tipo="qualificacao",
        data_prevista=hoje - timedelta(days=20),
        data_conclusao=hoje - timedelta(days=25),
        status="concluido",
    )
    m_artigo = Marco(
        orientacao_id=orientacao.id,
        titulo="Submissão de Artigo",
        tipo="publicacao",
        entrega_esperada="documento",
        data_prevista=hoje + timedelta(days=30),
        status="pendente",
    )
    m_outro = Marco(
        orientacao_id=orientacao.id,
        titulo="Apresentação em seminário",
        tipo="outro",
        data_prevista=hoje + timedelta(days=60),
        status="pendente",
    )
    db.session.add_all([m_qualif, m_artigo, m_outro])
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)

    # Pesos padrão do modelo 30/30/20/20
    assert resultado["pesos"] == {
        "atraso": 30,
        "ritmo": 30,
        "criticos": 20,
        "assiduidade": 20,
    }

    # Chaves do Earned Schedule
    assert "spi_t" in resultado
    assert "tspi" in resultado
    assert "perc_concluido_ponderado" in resultado
    assert "data_termino_projetada" in resultado
    assert "desvio_projetado_dias" in resultado

    # Ponderado (3.0 de 6.0 = 50%) difere de simples não ponderado (1 de 3 = 33%)
    assert resultado["perc_concluido_ponderado"] != resultado["perc_concluido"]
    assert resultado["perc_concluido_ponderado"] == 50
    assert resultado["perc_concluido"] == 33


def test_earned_schedule_ritmo_lento_spi_t_e_projecao_termino(app, orientacao):
    """Vínculo com ritmo lento: spi_t < 1.0, tspi > 1.0, data_termino_projetada preenchida e desvio > 0."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=150)
    orientacao.data_fim_prevista = hoje + timedelta(days=50)  # total 200 dias, 75% decorrido

    # Avanço baixo para 75% do tempo decorrido: apenas 1 marco de peso 1 concluído
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Planejamento",
        tipo="outro",
        data_prevista=hoje - timedelta(days=120),
        data_conclusao=hoje - timedelta(days=125),
        status="concluido",
    )
    m2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação",
        tipo="qualificacao",
        data_prevista=hoje - timedelta(days=20),
        status="pendente",
    )
    m3 = Marco(
        orientacao_id=orientacao.id,
        titulo="Defesa",
        tipo="defesa",
        data_prevista=hoje + timedelta(days=30),
        status="pendente",
    )
    db.session.add_all([m1, m2, m3])
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["spi_t"] < 1.0
    assert resultado["tspi"] > 1.0
    assert resultado["data_termino_projetada"] is not None
    assert resultado["data_termino_projetada"] > orientacao.data_fim_prevista
    assert resultado["desvio_projetado_dias"] > 0


def test_earned_schedule_em_dia_sem_desvio(app, orientacao):
    """Vínculo adiantado ou em dia: spi_t >= 1.0, sem data de término projetada e desvio zero."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=40)
    orientacao.data_fim_prevista = hoje + timedelta(days=160)  # total 200 dias, 20% decorrido

    # Avanço substancial logo no início (5 de 8 pesos concluídos: ~62.5% avanço com 20% do tempo)
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação antecipada",
        tipo="qualificacao",
        data_prevista=hoje - timedelta(days=10),
        data_conclusao=hoje - timedelta(days=15),
        status="concluido",
    )
    m2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Artigo submetido",
        tipo="publicacao",
        data_prevista=hoje + timedelta(days=20),
        data_conclusao=hoje - timedelta(days=5),
        status="concluido",
    )
    m3 = Marco(
        orientacao_id=orientacao.id,
        titulo="Defesa",
        tipo="defesa",
        data_prevista=hoje + timedelta(days=150),
        status="pendente",
    )
    db.session.add_all([m1, m2, m3])
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["spi_t"] >= 1.0
    assert resultado["data_termino_projetada"] is None
    assert resultado["desvio_projetado_dias"] == 0


def test_separacao_responsabilidade_marco_aguardando_orientador(app, orientacao):
    """Marco vencido aguardando orientador não penaliza orientando e recebe crédito parcial de 75%."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=60)
    orientacao.data_fim_prevista = hoje + timedelta(days=120)

    # Marco com prazo vencido, mas conclusão sinalizada pelo orientando
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Relatório anual entregue",
        tipo="relatorio",
        entrega_esperada="documento",
        data_prevista=hoje - timedelta(days=10),
        status="pendente",
        conclusao_sinalizada=True,
    )
    db.session.add(m)
    db.session.commit()
    assert m.aguardando == "orientador"

    resultado = painel.analisar_risco_prazos(orientacao)
    # Contabilizado na fila do orientador
    assert resultado["aguardando_orientador"] >= 1
    # Não contabilizado em atrasos sob responsabilidade do orientando
    atrasos_aluno = resultado.get("atrasos_orientando", 0)
    if isinstance(atrasos_aluno, (list, tuple)):
        assert len(atrasos_aluno) == 0
    else:
        assert atrasos_aluno == 0
    # Não gera pontuação de atraso para o orientando
    assert resultado["pts_atraso"] == 0
    # Recebe crédito parcial de 75% no avanço ponderado
    assert resultado["perc_concluido_ponderado"] > 0

    # Contraste: se a conclusão não foi sinalizada (aguardando orientando), há penalidade de atraso
    m.conclusao_sinalizada = False
    db.session.commit()
    assert m.aguardando == "orientando"

    res_aluno = painel.analisar_risco_prazos(orientacao)
    assert res_aluno["aguardando_orientador"] == 0
    atrasos_aluno_pend = res_aluno.get("atrasos_orientando", 0)
    if isinstance(atrasos_aluno_pend, (list, tuple)):
        assert len(atrasos_aluno_pend) >= 1
    else:
        assert atrasos_aluno_pend >= 1
    assert res_aluno["pts_atraso"] > 0


def test_atrito_retrabalho_parecer_desfavoravel_e_tarefa_devolvida(
    app, orientacao, orientador, orientando
):
    """Parecer desfavorável (reprovado/ressalvas) somado a tarefa devolvida eleva pts_criticos."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=60)
    orientacao.data_fim_prevista = hoje + timedelta(days=180)

    # Marco regular futuro
    m_regular = Marco(
        orientacao_id=orientacao.id,
        titulo="Capítulo 1",
        tipo="outro",
        data_prevista=hoje + timedelta(days=30),
        status="pendente",
    )
    db.session.add(m_regular)
    db.session.commit()

    base = painel.analisar_risco_prazos(orientacao)
    pts_base = base["pts_criticos"]

    # Adiciona documento com versão e parecer desfavorável (reprovado)
    doc = Documento(
        orientacao_id=orientacao.id,
        titulo="Relatório preliminar",
        criado_por=orientador.id,
    )
    db.session.add(doc)
    db.session.flush()

    v1 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        enviado_por=orientando.id,
        comentario="Versão 1 enviada",
    )
    db.session.add(v1)
    db.session.flush()

    parecer_reprovado = Parecer(
        orientacao_id=orientacao.id,
        versao_documento_id=v1.id,
        tipo="documento",
        conteudo="Reprovado: reformular metodologia e fundamentação teórica.",
        resultado="reprovado",
        emitido_por=orientador.id,
    )
    # E marco com devolução pendente (aguardando orientando_revisao)
    m_devolvido = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisão da metodologia",
        tipo="outro",
        data_prevista=hoje + timedelta(days=15),
        status="pendente",
        devolvido_em=datetime.now(UTC),
        nota_devolucao="Reescrever metodologia conforme parecer.",
    )
    db.session.add_all([parecer_reprovado, m_devolvido])
    db.session.commit()
    assert m_devolvido.aguardando == "orientando_revisao"

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pts_criticos"] > pts_base
    assert resultado["pts_criticos"] >= 10
    fatores_str = " ".join(resultado["fatores"]).lower()
    assert any(
        term in fatores_str
        for term in ("devolvida", "parecer", "revisão", "reprova", "ressalva")
    )

    # Também verifica com 'aprovado_com_ressalvas'
    parecer_reprovado.resultado = "aprovado_com_ressalvas"
    db.session.commit()
    resultado_ressalvas = painel.analisar_risco_prazos(orientacao)
    assert resultado_ressalvas["pts_criticos"] > pts_base


def test_faltas_consecutivas_penalizam_assiduidade(app, orientacao, orientador):
    """Atas consecutivas recentes com falta produzem faltas_consecutivas >= 3 e penalizam assiduidade."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=120)
    orientacao.data_fim_prevista = hoje + timedelta(days=180)

    # 4 atas cronológicas: 1ª presente, e as 3 últimas com falta consecutiva
    for i in range(4):
        presenca = "presente" if i == 0 else "ausente"
        ata = Ata(
            tipo="individual",
            orientador_id=orientador.id,
            data_reuniao=hoje - timedelta(days=60 - i * 15),
            pauta=f"Reunião de acompanhamento {i + 1}",
            deliberacoes="Registro de acompanhamento.",
            redigida_por=orientador.id,
            status="finalizada",
            participacoes=[
                AtaParticipacao(orientacao_id=orientacao.id, presenca=presenca)
            ],
        )
        db.session.add(ata)
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["faltas_consecutivas"] >= 3
    assert resultado["pts_assiduidade"] > 0
    fatores_str = " ".join(resultado["fatores"]).lower()
    assert any(term in fatores_str for term in ("ausên", "falta", "reuni"))


def test_janela_inatividade_eleva_risco_assiduidade(app, orientacao):
    """Orientação ativa sem atividade recente por mais de dias_inatividade_alerta (45d) eleva pts_assiduidade."""
    hoje = hoje_local()
    orientacao.data_inicio = hoje - timedelta(days=70)
    orientacao.data_fim_prevista = hoje + timedelta(days=200)

    # Apenas um marco futuro distante, sem conclusões, envios ou atas
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Depósito da dissertação",
        data_prevista=hoje + timedelta(days=120),
        status="pendente",
    )
    db.session.add(m)
    db.session.commit()

    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["dias_inatividade"] > 45
    assert resultado["pts_assiduidade"] > 0
    fatores_str = " ".join(resultado["fatores"]).lower()
    assert any(term in fatores_str for term in ("inatividade", "sem", "dia"))


def test_admin_configuracao_risco_persiste_parametros_completos_e_reflete_analise(
    client, app, admin, orientacao
):
    """POST em /admin/risco salva pesos, cortes e gatilhos e reflete imediatamente em analisar_risco_prazos."""
    login(client, admin.email)

    dados = {
        "limiar_medio": 75,
        "limiar_alto": 90,
        "tipos_criticos": ["qualificacao", "defesa"],
        "peso_atraso": 50,
        "peso_ritmo": 20,
        "peso_criticos": 15,
        "peso_assiduidade": 15,
        "nota_risco_moderado": 20,
        "nota_risco_alto": 40,
        "nota_risco_critico": 65,
        "dias_atraso_grave": 15,
        "janela_marco_critico_dias": 45,
        "dias_inatividade_alerta": 20,
        "tolerancia_ausencia_pct": 10,
    }

    resposta = client.post("/admin/risco", data=dados)
    assert resposta.status_code == 302

    config = ConfiguracaoRisco.vigente()
    assert config.criticos == ("qualificacao", "defesa")

    params = config.parametros_modelo
    if isinstance(params, str):
        params = json.loads(params)
    assert params["peso_atraso"] == 50
    assert params["peso_ritmo"] == 20
    assert params["peso_criticos"] == 15
    assert params["peso_assiduidade"] == 15
    assert params["nota_risco_moderado"] == 20
    assert params["nota_risco_alto"] == 40
    assert params["nota_risco_critico"] == 65
    assert params["dias_atraso_grave"] == 15
    assert params["janela_marco_critico_dias"] == 45
    assert params["dias_inatividade_alerta"] == 20
    assert params["tolerancia_ausencia_pct"] == 10

    # Reflete imediatamente na função de análise
    resultado = painel.analisar_risco_prazos(orientacao)
    assert resultado["pesos"] == {
        "atraso": 50,
        "ritmo": 20,
        "criticos": 15,
        "assiduidade": 15,
    }


def test_admin_configuracao_risco_validacao_soma_pesos(client, admin):
    """POST em /admin/risco com soma dos 4 pesos != 100 rejeita com validação e não salva."""
    login(client, admin.email)

    dados_invalidos = {
        "limiar_medio": 75,
        "limiar_alto": 90,
        "tipos_criticos": ["qualificacao"],
        "peso_atraso": 50,
        "peso_ritmo": 20,
        "peso_criticos": 15,
        "peso_assiduidade": 10,  # soma = 95 != 100
        "nota_risco_moderado": 25,
        "nota_risco_alto": 50,
        "nota_risco_critico": 75,
        "dias_atraso_grave": 15,
        "janela_marco_critico_dias": 30,
        "dias_inatividade_alerta": 45,
        "tolerancia_ausencia_pct": 20,
    }

    resposta = client.post("/admin/risco", data=dados_invalidos)
    assert resposta.status_code == 200  # re-renderiza com formulário e erro
    html = resposta.data.decode("utf-8", errors="ignore").lower()
    assert "100" in html or "peso" in html or "soma" in html

    config = db.session.get(ConfiguracaoRisco, 1)
    if config is not None and getattr(config, "parametros_modelo", None):
        params = config.parametros_modelo
        if isinstance(params, str):
            params = json.loads(params)
        assert params.get("peso_atraso") != 50 or params.get("peso_assiduidade") != 10


def test_admin_configuracao_risco_validacao_ordem_cortes(client, admin):
    """POST em /admin/risco com cortes fora de ordem crescente rejeita com validação e não salva."""
    login(client, admin.email)

    dados_invalidos = {
        "limiar_medio": 75,
        "limiar_alto": 90,
        "tipos_criticos": ["qualificacao"],
        "peso_atraso": 30,
        "peso_ritmo": 30,
        "peso_criticos": 20,
        "peso_assiduidade": 20,
        "nota_risco_moderado": 60,
        "nota_risco_alto": 40,  # inválido: moderado (60) > alto (40)
        "nota_risco_critico": 75,
        "dias_atraso_grave": 15,
        "janela_marco_critico_dias": 30,
        "dias_inatividade_alerta": 45,
        "tolerancia_ausencia_pct": 20,
    }

    resposta = client.post("/admin/risco", data=dados_invalidos)
    assert resposta.status_code == 200  # re-renderiza com formulário e erro
    html = resposta.data.decode("utf-8", errors="ignore").lower()
    assert (
        "corte" in html
        or "ordem" in html
        or "alto" in html
        or "moderado" in html
        or "maior" in html
    )

    config = db.session.get(ConfiguracaoRisco, 1)
    if config is not None and getattr(config, "parametros_modelo", None):
        params = config.parametros_modelo
        if isinstance(params, str):
            params = json.loads(params)
        assert (
            params.get("nota_risco_moderado") != 60
            or params.get("nota_risco_alto") != 40
        )
