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
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoRisco,
    Documento,
    Marco,
    Orientacao,
    Parecer,
    VersaoDocumento,
)
from app.services.rbac import orientacoes_do_usuario
from app.services.tempo import agora


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
    hoje = agora().date()
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


def pendencias() -> dict:
    ids = _ids_visiveis()
    if not ids:
        return {
            "entregas_a_confirmar": [],
            "tarefas_abertas": [],
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

    # ainda não entregue; as atrasadas vêm primeiro por ordem de prazo
    tarefas_abertas = (
        _com_orientando(Marco.query)
        .filter(
            Marco.orientacao_id.in_(ids),
            Marco.status != "concluido",
            Marco.conclusao_sinalizada.is_(False),
        )
        .order_by(Marco.data_prevista)
        .all()
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

    # apenas a versão corrente de cada documento: versões antigas sem parecer
    # não são pendência, foram superadas por outra versão
    com_parecer = select(Parecer.versao_documento_id).where(
        Parecer.versao_documento_id.isnot(None)
    )
    versao_corrente = (
        select(db.func.max(VersaoDocumento.numero_versao))
        .where(VersaoDocumento.documento_id == Documento.id)
        .correlate(Documento)
        .scalar_subquery()
    )
    versoes_sem_parecer = (
        VersaoDocumento.query.join(Documento, Documento.id == VersaoDocumento.documento_id)
        .options(joinedload(VersaoDocumento.documento).joinedload(Documento.orientacao))
        .filter(
            Documento.orientacao_id.in_(ids),
            VersaoDocumento.numero_versao == versao_corrente,
            VersaoDocumento.id.notin_(com_parecer),
        )
        .order_by(VersaoDocumento.enviado_em.desc())
        .all()
    )

    return {
        "entregas_a_confirmar": entregas_a_confirmar,
        "tarefas_abertas": tarefas_abertas,
        "reunioes_sem_ata": reunioes_sem_ata,
        "atas_rascunho": atas_rascunho,
        "versoes_sem_parecer": versoes_sem_parecer,
        # agenda, e não pendência: fica fora do total, que conta o que está
        # parado esperando ação
        "proximas_reunioes": proximas_reunioes,
        "total": (
            len(entregas_a_confirmar)
            + len(tarefas_abertas)
            + len(reunioes_sem_ata)
            + len(atas_rascunho)
            + len(versoes_sem_parecer)
        ),
    }
