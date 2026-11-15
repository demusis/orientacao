"""Qual versão de documento está à espera de parecer — a regra, num ponto só.

Painel, avisos por e-mail e indicadores do ciclo de avaliação respondem à mesma
pergunta. Quando cada um tinha a sua cópia da consulta, o indicador ficou para
trás das regras decididas depois (entrega da orientanda, devolução, versão só
comentário) e passou a contar o que a tela não mostrava — o número do ciclo
deixou de ser comparável com o que o orientador vê.
"""
from sqlalchemy import and_, func, or_, select

from app.models import Documento, Marco, Orientacao, Parecer, VersaoDocumento


def marco_aberto_da_versao(versao: VersaoDocumento | None) -> Marco | None:
    """Devolve o marco ainda não concluído ligado à versão (direto via
    `documento.marco` ou como texto a revisar via `Marco.documento_base_id`),
    ou None se não houver."""
    if versao is None or versao.documento is None:
        return None
    documento = versao.documento
    if documento.marco is not None and documento.marco.status != "concluido":
        return documento.marco
    return (
        Marco.query.filter_by(
            orientacao_id=documento.orientacao_id,
            documento_base_id=documento.id,
            entrega_esperada="revisao",
        )
        .filter(Marco.status != "concluido")
        .order_by(Marco.data_prevista)
        .first()
    )


def criterios_aguardando_parecer() -> list:
    """Filtros sobre `VersaoDocumento`. A consulta precisa juntar `Documento` e
    `Orientacao` — o critério compara o remetente com o orientando do vínculo."""
    com_parecer = select(Parecer.versao_documento_id).where(
        Parecer.versao_documento_id.isnot(None)
    )
    # apenas a versão corrente de cada documento: versões antigas sem parecer
    # não são pendência, foram superadas por outra versão
    versao_corrente = (
        select(func.max(VersaoDocumento.numero_versao))
        .where(VersaoDocumento.documento_id == Documento.id)
        .correlate(Documento)
        .scalar_subquery()
    )
    marcos_concluidos = select(Marco.id).where(Marco.status == "concluido")
    docs_em_revisao_aberta = select(Marco.documento_base_id).where(
        Marco.documento_base_id.isnot(None),
        Marco.status != "concluido",
        or_(
            Marco.criado_em.is_(None),
            VersaoDocumento.enviado_em >= Marco.criado_em,
        ),
    )
    marco_proprio_concluido = and_(
        Documento.marco_id.isnot(None),
        Documento.marco_id.in_(marcos_concluidos),
        Documento.id.notin_(docs_em_revisao_aberta),
    )
    marcos_devolvidos_apos_envio = select(Marco.id).where(
        Marco.status != "concluido",
        Marco.conclusao_sinalizada.is_(False),
        Marco.devolvido_em.isnot(None),
        Marco.devolvido_em >= VersaoDocumento.enviado_em,
    )
    docs_revisao_devolvidos_apos_envio = select(Marco.documento_base_id).where(
        Marco.documento_base_id.isnot(None),
        Marco.status != "concluido",
        Marco.conclusao_sinalizada.is_(False),
        Marco.devolvido_em.isnot(None),
        Marco.devolvido_em >= VersaoDocumento.enviado_em,
    )
    return [
        VersaoDocumento.numero_versao == versao_corrente,
        VersaoDocumento.id.notin_(com_parecer),
        # parecer é a avaliação da entrega da orientanda: entra a versão que ela
        # enviou — ou que o orientador registrou EM NOME dela. O upload comum do
        # orientador nunca cobra o parecer dele próprio.
        or_(
            VersaoDocumento.enviado_por == Orientacao.orientando_id,
            VersaoDocumento.em_nome_do_orientando.is_(True),
        ),
        VersaoDocumento.eh_devolucao.is_(False),
        # versão só comentário não tem o que avaliar
        VersaoDocumento.nome_fisico.isnot(None),
        # tarefa encerrada pela confirmação do marco (sem revisão aberta usando o
        # documento) ou devolvida para revisão após o envio desta versão não
        # segue cobrando parecer no Painel e nos e-mails
        ~marco_proprio_concluido,
        or_(
            Documento.marco_id.is_(None),
            Documento.marco_id.notin_(marcos_devolvidos_apos_envio),
        ),
        Documento.id.notin_(docs_revisao_devolvidos_apos_envio),
    ]
