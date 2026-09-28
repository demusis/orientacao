"""Qual versão de documento está à espera de parecer — a regra, num ponto só.

Painel, avisos por e-mail e indicadores do ciclo de avaliação respondem à mesma
pergunta. Quando cada um tinha a sua cópia da consulta, o indicador ficou para
trás das regras decididas depois (entrega da orientanda, devolução, versão só
comentário) e passou a contar o que a tela não mostrava — o número do ciclo
deixou de ser comparável com o que o orientador vê.
"""
from sqlalchemy import func, or_, select

from app.models import Documento, Orientacao, Parecer, VersaoDocumento


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
    ]
