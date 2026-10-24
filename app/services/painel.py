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
