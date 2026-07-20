"""Indicadores agregados do sistema, para o ciclo periódico de avaliação.

Distinguem-se de `services/painel.py`: aquele responde "o que *eu* tenho a
fazer" e filtra pelo usuário corrente; este responde "como o sistema está sendo
usado" e abrange toda a base, sem contexto de requisição — roda também por linha
de comando.

Só há agregação. Nenhuma leitura individual é registrada nem exposta: o que
interessa aqui é quantos, não quem fez o quê.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Ata,
    Documento,
    LogAuditoria,
    Marco,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Usuario,
    VersaoDocumento,
)

# Limiares em dias. Reunidos aqui para que o relatório possa citá-los.
OCIOSO_CURTO = 30
OCIOSO_LONGO = 90
RASCUNHO_VELHO = 15


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _naive(momento: datetime) -> datetime:
    """As colunas DateTime são gravadas sem fuso; comparar com valor ciente de
    fuso falharia no SQLite."""
    return momento.replace(tzinfo=None)


def _contar(consulta) -> int:
    return db.session.execute(consulta).scalar() or 0


def adesao() -> dict:
    """Quem tem conta e quem de fato entra."""
    limite_curto = _naive(_agora() - timedelta(days=OCIOSO_CURTO))
    limite_longo = _naive(_agora() - timedelta(days=OCIOSO_LONGO))

    por_papel = {
        papel: total
        for papel, total in db.session.execute(
            select(Usuario.papel, func.count()).group_by(Usuario.papel)
        ).all()
    }
    return {
        "contas_por_papel": por_papel,
        "contas_ativas": _contar(
            select(func.count()).select_from(Usuario).where(Usuario.ativo.is_(True))
        ),
        "contas_inativas": _contar(
            select(func.count()).select_from(Usuario).where(Usuario.ativo.is_(False))
        ),
        "nunca_acessaram": _contar(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.ativo.is_(True), Usuario.ultimo_acesso.is_(None))
        ),
        f"sem_acesso_ha_{OCIOSO_CURTO}d": _contar(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.ativo.is_(True), Usuario.ultimo_acesso < limite_curto)
        ),
        f"sem_acesso_ha_{OCIOSO_LONGO}d": _contar(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.ativo.is_(True), Usuario.ultimo_acesso < limite_longo)
        ),
    }


def vinculos() -> dict:
    """Vínculos por situação e os que não saíram do papel."""
    por_status = {
        status: total
        for status, total in db.session.execute(
            select(Orientacao.status, func.count()).group_by(Orientacao.status)
        ).all()
    }
    com_marco = select(Marco.orientacao_id).distinct()
    return {
        "por_status": por_status,
        "por_modalidade": {
            modalidade: total
            for modalidade, total in db.session.execute(
                select(Orientacao.modalidade, func.count()).group_by(
                    Orientacao.modalidade
                )
            ).all()
        },
        "ativos_sem_marco": _contar(
            select(func.count())
            .select_from(Orientacao)
            .where(Orientacao.status == "ativa", Orientacao.id.notin_(com_marco))
        ),
        "com_coorientador": _contar(
            select(func.count(func.distinct(OrientacaoOrientador.orientacao_id)))
        ),
    }


def fluxo_de_marcos() -> dict:
    """Onde os marcos emperram. O intervalo entre sinalizar e confirmar revela
    orientador que não fecha o ciclo."""
    hoje = _naive(_agora()).date()
    por_status = {
        status: total
        for status, total in db.session.execute(
            select(Marco.status, func.count()).group_by(Marco.status)
        ).all()
    }
    por_etapa = {
        etapa: total
        for etapa, total in db.session.execute(
            select(Marco.etapa, func.count()).group_by(Marco.etapa)
        ).all()
    }
    return {
        "total": _contar(select(func.count()).select_from(Marco)),
        "por_status": por_status,
        "por_etapa": por_etapa,
        "atrasados": _contar(
            select(func.count())
            .select_from(Marco)
            .where(Marco.status != "concluido", Marco.data_prevista < hoje)
        ),
        "aguardando_confirmacao": _contar(
            select(func.count())
            .select_from(Marco)
            .where(
                Marco.conclusao_sinalizada.is_(True), Marco.status != "concluido"
            )
        ),
        "sem_etapa_classificada": _contar(
            select(func.count()).select_from(Marco).where(Marco.etapa == 0)
        ),
    }


def documentos() -> dict:
    """Versão corrente sem parecer é trabalho entregue à espera de avaliação."""
    com_parecer = select(Parecer.versao_documento_id).where(
        Parecer.versao_documento_id.isnot(None)
    )
    versao_corrente = (
        select(func.max(VersaoDocumento.numero_versao))
        .where(VersaoDocumento.documento_id == Documento.id)
        .correlate(Documento)
        .scalar_subquery()
    )
    return {
        "documentos": _contar(select(func.count()).select_from(Documento)),
        "versoes": _contar(select(func.count()).select_from(VersaoDocumento)),
        "pareceres": _contar(select(func.count()).select_from(Parecer)),
        "versoes_correntes_sem_parecer": _contar(
            select(func.count())
            .select_from(VersaoDocumento)
            .join(Documento, Documento.id == VersaoDocumento.documento_id)
            .where(
                VersaoDocumento.numero_versao == versao_corrente,
                VersaoDocumento.id.notin_(com_parecer),
            )
        ),
    }


def atas() -> dict:
    """Rascunho antigo indica reunião registrada e nunca formalizada."""
    limite = _naive(_agora() - timedelta(days=RASCUNHO_VELHO))
    return {
        "por_status": {
            status: total
            for status, total in db.session.execute(
                select(Ata.status, func.count()).group_by(Ata.status)
            ).all()
        },
        "por_tipo": {
            tipo: total
            for tipo, total in db.session.execute(
                select(Ata.tipo, func.count()).group_by(Ata.tipo)
            ).all()
        },
        f"rascunhos_ha_mais_de_{RASCUNHO_VELHO}d": _contar(
            select(func.count())
            .select_from(Ata)
            .where(Ata.status == "rascunho", Ata.criada_em < limite)
        ),
    }


def trilha(dias: int = 30) -> dict:
    """Ações efetivamente ocorridas na janela. O vocabulário vem do banco, não
    de lista fixa no código: ação nova aparece sozinha."""
    limite = _naive(_agora() - timedelta(days=dias))
    ocorrencias = db.session.execute(
        select(LogAuditoria.acao, func.count())
        .where(LogAuditoria.timestamp >= limite)
        .group_by(LogAuditoria.acao)
        .order_by(func.count().desc())
    ).all()
    return {
        "janela_dias": dias,
        "registros_no_periodo": sum(total for _, total in ocorrencias),
        "registros_totais": _contar(select(func.count()).select_from(LogAuditoria)),
        "acoes_no_periodo": {acao: total for acao, total in ocorrencias},
        "acoes_ja_registradas": sorted(
            acao
            for (acao,) in db.session.execute(
                select(LogAuditoria.acao).distinct()
            ).all()
        ),
        "origens_distintas": _contar(
            select(func.count(func.distinct(LogAuditoria.ip))).where(
                LogAuditoria.timestamp >= limite
            )
        ),
    }


def coletar(dias: int = 30) -> dict:
    """Snapshot completo. O relatório de avaliação guarda este dicionário para
    que o ciclo seguinte compare e afirme se algo melhorou."""
    return {
        "gerado_em": _agora().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "janela_dias": dias,
        "adesao": adesao(),
        "vinculos": vinculos(),
        "marcos": fluxo_de_marcos(),
        "documentos": documentos(),
        "atas": atas(),
        "trilha": trilha(dias),
    }
