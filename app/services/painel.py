"""Pendências do painel: o que está parado esperando ação de alguém.

Reúne, nos vínculos ativos visíveis ao usuário corrente, as entregas
sinalizadas à espera de confirmação, as tarefas em aberto, as atas ainda em
rascunho e as versões de documento sem parecer. Cada categoria é obtida em uma
única consulta — percorrer `orientacao.marcos` por vínculo dispararia uma
consulta por orientação, pois o relacionamento é `lazy="dynamic"`."""
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    Documento,
    Marco,
    Orientacao,
    Parecer,
    VersaoDocumento,
)
from app.services.rbac import orientacoes_do_usuario


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
            "atas_rascunho": [],
            "versoes_sem_parecer": [],
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

    atas_rascunho = (
        Ata.query.join(AtaParticipacao, AtaParticipacao.ata_id == Ata.id)
        .filter(
            AtaParticipacao.orientacao_id.in_(ids),
            Ata.status == "rascunho",
        )
        .order_by(Ata.data_reuniao.desc())
        .distinct()
        .all()
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
        "atas_rascunho": atas_rascunho,
        "versoes_sem_parecer": versoes_sem_parecer,
        "total": (
            len(entregas_a_confirmar)
            + len(tarefas_abertas)
            + len(atas_rascunho)
            + len(versoes_sem_parecer)
        ),
    }
