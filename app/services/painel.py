"""Pendências do painel: o que está parado esperando ação de alguém.

Reúne, nos vínculos ativos visíveis ao usuário corrente, as entregas
sinalizadas à espera de confirmação, as tarefas em aberto, as reuniões já
realizadas sem ata, as atas ainda em rascunho e as versões de documento sem
parecer. Cada categoria é obtida em uma única consulta: percorrer
`orientacao.marcos` por vínculo dispararia uma consulta por orientação, pois o
relacionamento é `lazy="dynamic"`.

Devolve ainda `proximas_reunioes`, que é agenda e não pendência, e por isso não
entra no total: reunião marcada para a semana que vem não está parada esperando
ninguém."""
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import joinedload

from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoRisco,
    Documento,
    Marco,
    Orientacao,
    VersaoDocumento,
)
from app.services.pareceres import criterios_aguardando_parecer
from app.services.rbac import orientacoes_do_usuario
from app.services.tempo import hoje_local


def relogio(orientacao) -> dict:
    """Situação do vínculo no tempo do programa: quanto do prazo já decorreu e um
    sinal de risco, para o orientador ver de relance quem se aproxima do fim sem
    ter cumprido os marcos que importam.

    O risco combina tempo e marco: **alto** (vermelho) quando um marco crítico
    está vencido e não concluído, ou quando o prazo decorrido passou do limiar
    alto; **médio** (amarelo) acima do limiar médio; **baixo** no restante.
    Limiar (padrão 90%/75%) e tipos críticos (padrão qualificação e defesa) são
    os de `ConfiguracaoRisco`, editáveis pelo administrador. Sem
    `data_fim_prevista` não há fração de prazo, e o risco fica só a cargo dos
    marcos críticos — o rótulo então diz "prazo não definido"."""
    config = ConfiguracaoRisco.vigente()
    # dia local: data de início e fim previsto são datas de parede digitadas
    hoje = hoje_local()
    inicio = orientacao.data_inicio
    fim = orientacao.data_fim_prevista
    dias_decorridos = max((hoje - inicio).days, 0)
    meses_decorridos = dias_decorridos // 30

    fracao = meses_total = dias_restantes = None
    if fim and fim > inicio:
        fracao = dias_decorridos / (fim - inicio).days
        meses_total = max(round((fim - inicio).days / 30), 1)
        dias_restantes = (fim - hoje).days

    # reaproveita Marco.atrasado (status != concluído e data prevista já passou)
    marco_critico_vencido = any(
        m.atrasado for m in orientacao.marcos if m.tipo in config.criticos
    )

    if marco_critico_vencido or (fracao is not None and fracao > config.limiar_alto / 100):
        risco = "alto"
    elif fracao is not None and fracao > config.limiar_medio / 100:
        risco = "medio"
    else:
        risco = "baixo"

    if meses_total:
        rotulo = f"mês {min(meses_decorridos, meses_total)} de {meses_total}"
    else:
        rotulo = f"{meses_decorridos} mês(es) · prazo não definido"

    return {
        "meses_decorridos": meses_decorridos,
        "meses_total": meses_total,
        "dias_restantes": dias_restantes,
        "risco": risco,
        "marco_critico_vencido": marco_critico_vencido,
        "rotulo": rotulo,
        "sem_prazo": fim is None,
    }


NIVEL_RISCO_PRAZO_LABEL = {
    "baixo": "Baixo",
    "medio": "Moderado",
    "alto": "Alto",
    "critico": "Crítico",
}


def _peso_marco(m: Marco, criticos: tuple[str, ...]) -> float:
    if m.tipo in criticos:
        return 3.0
    if (m.entrega_esperada in ("documento", "revisao")) or (
        m.tipo in ("artigo", "publicacao", "relatorio")
    ):
        return 2.0
    return 1.0


def analisar_risco_prazos(orientacao, marcos=None, atas=None) -> dict:
    """Avalia e pontua (0 a 100) o risco de não cumprimento dos prazos do vínculo.

    Implementa a metodologia Earned Schedule (ES) combinada com Early Warning
    System (EWS), calibrada por ConfiguracaoRisco.
    """
    config = ConfiguracaoRisco.vigente()
    hoje = hoje_local()
    if marcos is None:
        marcos = (
            orientacao.marcos.all()
            if hasattr(orientacao.marcos, "all")
            else list(orientacao.marcos)
        )
    if atas is None:
        atas = (
            orientacao.atas.all()
            if hasattr(orientacao.atas, "all")
            else list(orientacao.atas)
        )

    total_m = len(marcos)
    concluidos = [m for m in marcos if m.status == "concluido"]
    em_aberto = [m for m in marcos if m.status != "concluido"]

    # Pesos dos marcos e crédito de execução (Earned Schedule EV)
    peso_total = 0.0
    peso_ganho = 0.0
    atrasados_orientando = []
    aguardando_orientador = 0

    for m in marcos:
        w = _peso_marco(m, config.criticos)
        peso_total += w
        if m.status == "concluido":
            peso_ganho += 1.0 * w
        elif m.aguardando == "orientador":
            peso_ganho += 0.75 * w
            aguardando_orientador += 1
        else:
            if m.atrasado:
                atrasados_orientando.append(m)

    fracao_concluida = (len(concluidos) / total_m) if total_m > 0 else 0.0
    fracao_ponderada = (peso_ganho / peso_total) if peso_total > 0 else 0.0
    perc_concluido = round(fracao_concluida * 100) if total_m else 0
    perc_concluido_ponderado = (
        round(fracao_ponderada * 100) if peso_total > 0 else (100 if not total_m else 0)
    )

    inicio = orientacao.data_inicio
    fim = orientacao.data_fim_prevista
    duracao_planejada = (fim - inicio).days if (fim and inicio) else 0

    dias_decorridos = max((hoje - inicio).days, 0) if inicio else 0
    fracao_tempo = dias_restantes = None
    if fim and inicio and duracao_planejada > 0:
        fracao_tempo = dias_decorridos / duracao_planejada
        dias_restantes = (fim - hoje).days

    # Indicadores Earned Schedule
    spi_t = tspi = data_termino_projetada = None
    desvio_projetado_dias = 0

    if fim and inicio and duracao_planejada > 0:
        es_dias = fracao_ponderada * duracao_planejada
        at_dias = max(dias_decorridos, 1)
        spi_t = round(es_dias / at_dias, 2) if dias_decorridos > 0 else 1.0
        if dias_restantes is not None and dias_restantes > 0:
            tspi = round(max(0.0, duracao_planejada - es_dias) / dias_restantes, 2)
        else:
            tspi = 9.99 if em_aberto else 1.0

        if (
            fracao_tempo is not None
            and fracao_tempo > 0
            and em_aberto
            and spi_t < 0.98
            and total_m > 0
        ):
            duracao_estimada = round(duracao_planejada / max(spi_t, 0.25))
            data_termino_projetada = inicio + timedelta(days=duracao_estimada)
            desvio_projetado_dias = max(0, (data_termino_projetada - fim).days)

    P_atraso = config.peso_atraso
    P_ritmo = config.peso_ritmo
    P_crit = config.peso_criticos
    P_assid = config.peso_assiduidade

    # Vínculo já concluído não possui risco ativo de descumprimento
    if orientacao.status == "concluida":
        return {
            "pontuacao": 0,
            "nivel": "baixo",
            "cor_badge": "baixo",
            "rotulo": NIVEL_RISCO_PRAZO_LABEL["baixo"],
            "pts_atraso": 0,
            "pts_ritmo": 0,
            "pts_criticos": 0,
            "pts_assiduidade": 0,
            "maior_atraso_dias": 0,
            "perc_tempo": (
                round(min(fracao_tempo, 1.0) * 100)
                if fracao_tempo is not None
                else None
            ),
            "perc_concluido": round(fracao_concluida * 100) if total_m else 100,
            "fatores": ["Vínculo concluído."],
            "perc_concluido_ponderado": (
                100 if (not total_m or fracao_concluida == 1.0) else perc_concluido_ponderado
            ),
            "spi_t": 1.0,
            "tspi": 1.0,
            "data_termino_projetada": None,
            "desvio_projetado_dias": 0,
            "atrasos_orientando": 0,
            "aguardando_orientador": 0,
            "faltas_consecutivas": 0,
            "dias_inatividade": None,
            "pesos": {
                "atraso": P_atraso,
                "ritmo": P_ritmo,
                "criticos": P_crit,
                "assiduidade": P_assid,
            },
        }

    fatores: list[str] = []

    # 1. Dimensão Atrasos e Severidade (0..P_atraso)
    maior_atraso_dias = 0
    marco_mais_atrasado = None
    pts_atraso = 0
    if atrasados_orientando:
        marco_mais_atrasado = min(
            atrasados_orientando, key=lambda m: (m.data_prevista, m.id)
        )
        maior_atraso_dias = max((hoje - marco_mais_atrasado.data_prevista).days, 1)
        peso_atrasado = sum(
            _peso_marco(m, config.criticos) for m in atrasados_orientando
        )
        prop_simples = (len(atrasados_orientando) / total_m) if total_m else 0.0
        prop_ponderada = (peso_atrasado / peso_total) if peso_total > 0 else 0.0
        curva_idade = min(1.0, maior_atraso_dias / max(config.dias_atraso_grave, 1))
        f_atraso = min(
            1.0, prop_simples * 0.8 + prop_ponderada * 0.4 + 0.45 * curva_idade
        )
        pts_atraso = min(P_atraso, round(f_atraso * P_atraso))
        fatores.append(
            f"{len(atrasados_orientando)} de {total_m} marco(s) em atraso "
            f"(maior atraso: {maior_atraso_dias} dia(s) em «{marco_mais_atrasado.titulo}»)."
        )

    if aguardando_orientador > 0:
        fatores.append(
            f"{aguardando_orientador} entrega(s) aguardando validação do orientador."
        )

    # 2. Dimensão Ritmo Earned Schedule vs. Prazo (0..P_ritmo)
    pts_ritmo = 0
    perc_tempo = (
        round(min(max(fracao_tempo, 0.0), 1.0) * 100)
        if fracao_tempo is not None
        else None
    )
    if fracao_tempo is not None:
        defasagem = (
            max(0.0, min(fracao_tempo, 1.0) - min(fracao_concluida, fracao_ponderada))
            if total_m > 0
            else 0.0
        )
        pts_defasagem = min(20.0, defasagem * 35.0)
        pts_tspi = (
            min(6.0, max(0.0, (tspi - 1.0) * 3.0))
            if (tspi is not None and tspi > 1.10)
            else 0.0
        )
        if dias_restantes is not None and dias_restantes < 0 and (em_aberto or not total_m):
            pts_prazo = 10.0
            fatores.append(
                f"Prazo final previsto vencido há {-dias_restantes} dia(s) "
                f"com {len(em_aberto)} marco(s) ainda em aberto."
            )
        elif fracao_tempo > config.limiar_alto / 100:
            pts_prazo = 10.0
        elif fracao_tempo > config.limiar_medio / 100:
            pts_prazo = 6.0
        else:
            pts_prazo = 0.0

        if (
            spi_t is not None
            and spi_t >= 1.0
            and not atrasados_orientando
            and fracao_ponderada >= min(fracao_tempo, 1.0)
        ):
            pts_ritmo = 0
        else:
            pts_base_ritmo = min(30.0, pts_defasagem + pts_tspi + pts_prazo)
            pts_ritmo = (
                min(P_ritmo, round(pts_base_ritmo * (P_ritmo / 30.0)))
                if P_ritmo > 0
                else 0
            )

        if defasagem >= 0.15 and total_m:
            restantes_txt = (
                f", restando {len(em_aberto)} tarefa(s) para {max(dias_restantes, 0)} dia(s)"
                if dias_restantes is not None and dias_restantes >= 0
                else ""
            )
            fatores.append(
                f"Descompasso entre tempo e entregas: {perc_tempo}% do prazo decorrido "
                f"versus {perc_concluido}% do cronograma concluído{restantes_txt}."
            )

        if desvio_projetado_dias > 0 and data_termino_projetada is not None:
            fatores.append(
                f"Projeção Earned Schedule: SPI(t)={spi_t:.2f}, término estimado em "
                f"{data_termino_projetada:%d/%m/%Y} (+{desvio_projetado_dias} dia(s) de desvio)."
            )
    elif total_m:
        previstos_ate_hoje = [m for m in marcos if m.data_prevista <= hoje]
        if previstos_ate_hoje and atrasados_orientando:
            pts_base_ritmo = min(
                25.0, (len(atrasados_orientando) / len(previstos_ate_hoje)) * 25.0
            )
            pts_ritmo = (
                min(P_ritmo, round(pts_base_ritmo * (P_ritmo / 30.0)))
                if P_ritmo > 0
                else 0
            )

    # 3. Dimensão Marcos Críticos e Retrabalho (0..P_crit)
    criticos_vencidos = [
        m
        for m in em_aberto
        if m.atrasado
        and m.tipo in config.criticos
        and m.aguardando != "orientador"
    ]
    criticos_proximos = [
        m
        for m in em_aberto
        if not m.atrasado
        and m.tipo in config.criticos
        and 0 <= (m.data_prevista - hoje).days <= config.janela_marco_critico_dias
    ]
    devolvidos = [m for m in em_aberto if m.aguardando == "orientando_revisao"]

    pareceres_vinculo = (
        orientacao.pareceres.all()
        if hasattr(orientacao.pareceres, "all")
        else list(orientacao.pareceres)
    )
    reprovados = [p for p in pareceres_vinculo if p.resultado == "reprovado"]
    ressalvas = [p for p in pareceres_vinculo if p.resultado == "aprovado_com_ressalvas"]
    pts_pareceres = min(8, len(reprovados) * 6 + len(ressalvas) * 2)

    pts_base_crit = (
        (15 if criticos_vencidos else 0)
        + (5 if criticos_proximos else 0)
        + min(10, len(devolvidos) * 5)
        + pts_pareceres
    )
    pts_criticos = (
        min(P_crit, round(min(20, pts_base_crit) * (P_crit / 20.0)))
        if P_crit > 0
        else 0
    )

    for m in criticos_vencidos:
        fatores.append(
            f"Marco crítico vencido: «{m.titulo}» (previsto para {m.data_prevista:%d/%m/%Y})."
        )
    for m in criticos_proximos:
        dias_m = (m.data_prevista - hoje).days
        fatores.append(
            f"Marco crítico próximo: «{m.titulo}» vence em {dias_m} dia(s) ({m.data_prevista:%d/%m/%Y})."
        )
    if devolvidos:
        fatores.append(
            f"{len(devolvidos)} tarefa(s) devolvida(s) aguardando revisão e reenvio pelo orientando."
        )
    if reprovados:
        fatores.append(
            f"{len(reprovados)} parecer(es) com resultado reprovado no vínculo."
        )
    elif ressalvas:
        fatores.append(
            f"{len(ressalvas)} parecer(es) aprovado(s) com ressalvas no vínculo."
        )

    # 4. Dimensão Engajamento, Assiduidade e Atividade (0..P_assid)
    presentes = ausencias = 0
    atas_apuradas = []
    for a in atas:
        if a.status == "cancelada":
            continue
        part = a.participacao_de(orientacao.id)
        if part is not None and part.presenca in ("presente", "ausente"):
            atas_apuradas.append((a, part.presenca))
            if part.presenca == "presente":
                presentes += 1
            elif part.presenca == "ausente":
                ausencias += 1

    apuradas = presentes + ausencias
    atas_ordenadas = sorted(
        atas_apuradas,
        key=lambda x: (x[0].data_reuniao, x[0].id or 0),
        reverse=True,
    )
    faltas_consecutivas = 0
    for _, presenca in atas_ordenadas:
        if presenca == "ausente":
            faltas_consecutivas += 1
        else:
            break

    pts_faltas = 0
    taxa_ausencia = 0.0
    if apuradas >= 2 and ausencias > 0:
        taxa_ausencia = ausencias / apuradas
        taxa_pct = taxa_ausencia * 100
        bonus_consecutivas = 2 if faltas_consecutivas >= 3 else 0
        if taxa_pct > config.tolerancia_ausencia_pct:
            pts_faltas = min(15, round(taxa_ausencia * 20) + bonus_consecutivas)
        else:
            pts_faltas = min(3, round(taxa_ausencia * 8) + bonus_consecutivas)

        if taxa_ausencia >= 0.3:
            fatores.append(
                f"Ausência em reuniões: {ausencias} falta(s) em {apuradas} reunião(ões) "
                f"com presença registrada ({round(taxa_ausencia * 100)}%)."
            )

    # Inatividade
    datas_atividades = []
    for m in marcos:
        if m.data_conclusao and m.data_conclusao <= hoje:
            datas_atividades.append(m.data_conclusao)
        elif getattr(m, "concluido_em", None):
            dt_m = (
                m.concluido_em.date()
                if hasattr(m.concluido_em, "date")
                else m.concluido_em
            )
            if dt_m <= hoje:
                datas_atividades.append(dt_m)

    docs = (
        orientacao.documentos.all()
        if hasattr(orientacao.documentos, "all")
        else list(orientacao.documentos)
    )
    for d in docs:
        vers = d.versoes.all() if hasattr(d.versoes, "all") else list(d.versoes)
        for v in vers:
            if (
                v.enviada_pela_orientanda
                or v.em_nome_do_orientando
                or v.enviado_por == orientacao.orientando_id
            ):
                dt_v = (
                    v.enviado_em.date()
                    if hasattr(v.enviado_em, "date")
                    else v.enviado_em
                )
                if dt_v <= hoje:
                    datas_atividades.append(dt_v)

    for a, p in atas_apuradas:
        if p == "presente" and a.data_reuniao <= hoje:
            datas_atividades.append(a.data_reuniao)

    dias_inatividade = None
    if em_aberto:
        if datas_atividades:
            ultima_data = max(datas_atividades)
            dias_inatividade = max(0, (hoje - ultima_data).days)
        elif orientacao.data_inicio and orientacao.data_inicio <= hoje:
            dias_inatividade = max(0, (hoje - orientacao.data_inicio).days)

    pts_inatividade = 0
    if (
        dias_inatividade is not None
        and dias_inatividade > config.dias_inatividade_alerta
        and em_aberto
    ):
        pts_inatividade = 4
        fatores.append(
            f"Inatividade do orientando: {dias_inatividade} dia(s) sem entregas, "
            f"conclusões ou reuniões com presença (limite de alerta: {config.dias_inatividade_alerta} dias)."
        )

    pts_base_assid = pts_faltas + pts_inatividade
    pts_assiduidade = (
        min(P_assid, round(min(15, pts_base_assid) * (P_assid / 15.0)))
        if P_assid > 0
        else 0
    )

    # Classificação e pisos
    pontuacao = min(100, pts_atraso + pts_ritmo + pts_criticos + pts_assiduidade)
    if criticos_vencidos or (
        dias_restantes is not None and dias_restantes < 0 and em_aberto
    ):
        pontuacao = max(pontuacao, config.nota_risco_critico)

    if pontuacao >= config.nota_risco_critico:
        nivel = "critico"
        cor_badge = "alto"
    elif pontuacao >= config.nota_risco_alto:
        nivel = "alto"
        cor_badge = "alto"
    elif pontuacao >= config.nota_risco_moderado:
        nivel = "medio"
        cor_badge = "medio"
    else:
        nivel = "baixo"
        cor_badge = "baixo"

    if not fatores:
        fatores.append(
            "Cronograma em dia, sem atrasos ou alertas relevantes de prazo no momento."
        )

    return {
        "pontuacao": pontuacao,
        "nivel": nivel,
        "cor_badge": cor_badge,
        "rotulo": NIVEL_RISCO_PRAZO_LABEL[nivel],
        "pts_atraso": pts_atraso,
        "pts_ritmo": pts_ritmo,
        "pts_criticos": pts_criticos,
        "pts_assiduidade": pts_assiduidade,
        "maior_atraso_dias": maior_atraso_dias,
        "perc_tempo": perc_tempo,
        "perc_concluido": perc_concluido,
        "fatores": fatores,
        "perc_concluido_ponderado": perc_concluido_ponderado,
        "spi_t": spi_t,
        "tspi": tspi,
        "data_termino_projetada": data_termino_projetada,
        "desvio_projetado_dias": desvio_projetado_dias,
        "atrasos_orientando": len(atrasados_orientando),
        "aguardando_orientador": aguardando_orientador,
        "faltas_consecutivas": faltas_consecutivas,
        "dias_inatividade": dias_inatividade,
        "pesos": {
            "atraso": P_atraso,
            "ritmo": P_ritmo,
            "criticos": P_crit,
            "assiduidade": P_assid,
        },
    }


def _ids_visiveis() -> list[int]:
    """Vínculos ativos que o usuário corrente enxerga. Pendência de vínculo
    encerrado não é acionável e por isso fica de fora."""
    return [
        o.id for o in orientacoes_do_usuario().filter(Orientacao.status == "ativa")
    ]


def _com_orientando(consulta):
    """Evita N+1 ao exibir o nome do orientando em cada linha."""
    return consulta.options(
        joinedload(Marco.orientacao).joinedload(Orientacao.orientando)
    )


# "Tarefas a fazer": à vista só as atrasadas e as de prazo próximo; o resto vai
# recolhido. Com cronogramas inteiros cadastrados de uma vez (14 tarefas por
# aluno), a lista completa afogava o que vence agora.
JANELA_A_FAZER_DIAS = 30


@dataclass
class LinhaTarefa:
    """Uma linha de "Tarefas a fazer": um marco, ou — para quem orienta — os
    marcos de uma mesma tarefa em grupo, numa linha só."""

    marcos: list = field(default_factory=list)

    @property
    def principal(self):
        return min(self.marcos, key=lambda m: (m.data_prevista, m.id))

    @property
    def grupo(self) -> bool:
        return len(self.marcos) > 1

    @property
    def prazo(self):
        return self.principal.data_prevista

    @property
    def atrasado(self) -> bool:
        return any(m.atrasado for m in self.marcos)


def agrupar_linhas(marcos, agrupar_grupos: bool) -> list[LinhaTarefa]:
    """Uma linha por marco; com `agrupar_grupos`, os marcos de mesmo `grupo_id`
    viram uma linha. Preserva a ordem de prazo."""
    linhas: list[LinhaTarefa] = []
    por_grupo: dict[str, LinhaTarefa] = {}
    for m in marcos:
        if agrupar_grupos and m.grupo_id:
            if m.grupo_id in por_grupo:
                por_grupo[m.grupo_id].marcos.append(m)
                continue
            por_grupo[m.grupo_id] = LinhaTarefa([m])
            linhas.append(por_grupo[m.grupo_id])
        else:
            linhas.append(LinhaTarefa([m]))
    return linhas


def dividir_por_prazo(linhas, hoje=None):
    """(à vista, recolhidas): à vista as atrasadas e as de prazo até
    `JANELA_A_FAZER_DIAS`; as demais, recolhidas."""
    limite = (hoje or hoje_local()) + timedelta(days=JANELA_A_FAZER_DIAS)
    vista = [linha for linha in linhas if linha.atrasado or linha.prazo <= limite]
    depois = [linha for linha in linhas if linha not in vista]
    return vista, depois


def pendencias() -> dict:
    ids = _ids_visiveis()
    if not ids:
        return {
            "entregas_a_confirmar": [],
            "tarefas_a_fazer": [],
            "linhas_a_fazer": [],
            "linhas_a_fazer_depois": [],
            "tarefas_devolvidas": [],
            "reunioes_sem_ata": [],
            "atas_rascunho": [],
            "versoes_sem_parecer": [],
            "proximas_reunioes": [],
            "total": 0,
        }

    # entregue pelo orientando, aguardando confirmação do orientador
    entregas_a_confirmar = (
        _com_orientando(Marco.query)
        .filter(
            Marco.orientacao_id.in_(ids),
            Marco.conclusao_sinalizada.is_(True),
            Marco.status != "concluido",
        )
        .order_by(Marco.data_prevista)
        .all()
    )

    # ainda não entregue, partido em duas filas que pedem coisas diferentes:
    # a fazer (primeira entrega) e devolvidas (corrigir e reenviar). Juntas, a
    # devolução — que tem nota e urgência própria — se perdia entre as demais.
    # As atrasadas vêm primeiro, por ordem de prazo.
    abertas = (
        _com_orientando(Marco.query)
        .filter(
            Marco.orientacao_id.in_(ids),
            Marco.status != "concluido",
            Marco.conclusao_sinalizada.is_(False),
        )
        .order_by(Marco.data_prevista)
        .all()
    )
    tarefas_devolvidas = [m for m in abertas if m.aguardando == "orientando_revisao"]
    tarefas_a_fazer = [m for m in abertas if m.aguardando == "orientando"]
    # quem orienta vê a tarefa em grupo numa linha só; o orientando só tem a sua
    from flask_login import current_user

    linhas_a_fazer, linhas_a_fazer_depois = dividir_por_prazo(
        agrupar_linhas(tarefas_a_fazer, current_user.papel != "orientando")
    )

    # Toda reunião em rascunho dos vínculos visíveis, partida em seguida por
    # estado. Uma consulta só: filtrar "já realizada" em SQL exigiria comparar
    # data e hora, e a regra (hora desconhecida não é zero) já está na
    # propriedade `Ata.realizada`.
    rascunhos = (
        Ata.query.join(AtaParticipacao, AtaParticipacao.ata_id == Ata.id)
        .filter(
            AtaParticipacao.orientacao_id.in_(ids),
            Ata.status == "rascunho",
        )
        .order_by(Ata.data_reuniao.desc())
        .distinct()
        .all()
    )
    # Reunião marcada para daqui a duas semanas não é pendência: não há o que
    # fazer com ela ainda. Antes desta divisão ela figurava como "ata em
    # rascunho a finalizar" desde o instante do agendamento.
    reunioes_sem_ata = [a for a in rascunhos if a.realizada and not a.ata_redigida]
    atas_rascunho = [a for a in rascunhos if a.realizada and a.ata_redigida]
    proximas_reunioes = sorted(
        (a for a in rascunhos if a.agendada), key=lambda a: a.data_reuniao
    )

    versoes_sem_parecer = (
        VersaoDocumento.query.join(Documento, Documento.id == VersaoDocumento.documento_id)
        .join(Orientacao, Orientacao.id == Documento.orientacao_id)
        .options(joinedload(VersaoDocumento.documento).joinedload(Documento.orientacao))
        .filter(
            Documento.orientacao_id.in_(ids),
            *criterios_aguardando_parecer(),
        )
        .order_by(VersaoDocumento.enviado_em.desc())
        .all()
    )

    return {
        "entregas_a_confirmar": entregas_a_confirmar,
        "tarefas_a_fazer": tarefas_a_fazer,
        "linhas_a_fazer": linhas_a_fazer,
        "linhas_a_fazer_depois": linhas_a_fazer_depois,
        "tarefas_devolvidas": tarefas_devolvidas,
        "reunioes_sem_ata": reunioes_sem_ata,
        "atas_rascunho": atas_rascunho,
        "versoes_sem_parecer": versoes_sem_parecer,
        # agenda, e não pendência: fica fora do total, que conta o que está
        # parado esperando ação
        "proximas_reunioes": proximas_reunioes,
        "total": (
            len(entregas_a_confirmar)
            + len(tarefas_a_fazer)
            + len(tarefas_devolvidas)
            + len(reunioes_sem_ata)
            + len(atas_rascunho)
            + len(versoes_sem_parecer)
        ),
    }
