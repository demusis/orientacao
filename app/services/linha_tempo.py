"""Linha do tempo de um vínculo: marcos, entregas, pareceres e reuniões numa só
cronologia, com os vínculos entre eles.

As quatro abas (Cronograma, Documentos, Atas, Pareceres) respondem "o que existe
deste tipo?". Esta visão responde "o que aconteceu, e em que ordem?" — a pergunta
da banca e do relatório. Não substitui as abas, onde se opera; atravessa-as, onde
se lê a história.

Cada evento leva o instante que o posiciona, um rótulo, o caminho para o registro
real e as ligações que o tornam relacional (o parecer sabe a versão que avaliou;
a entrega, o marco a que pertence; a reunião, os marcos que discutiu). Sem essas
ligações seria um extrato; com elas, cada ponto conhece os outros a que se liga.
"""
from datetime import datetime, time

from app.models.ata import RESULTADO_LABEL

# tipos de evento, com rótulo curto para o filtro da tela
TIPOS = {
    "marco_previsto": "Marco previsto",
    "marco_concluido": "Marco concluído",
    "entrega": "Entrega de documento",
    "parecer": "Parecer",
    "reuniao": "Reunião",
}


def _dt(valor):
    """Normaliza para datetime: Date vira meia-noite (ingênuo), para ordenar
    junto dos DateTime. Só ordena; não é exibido."""
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    return datetime.combine(valor, time.min)


def eventos(orientacao) -> list:
    """Lista de eventos do vínculo, do mais recente ao mais antigo.

    Cada item é um dict: tipo, quando (datetime de ordenação), data (para exibir),
    titulo, detalhe, alvo (endpoint + args para link) e relacionados (texto)."""
    itens = []

    for m in orientacao.marcos:
        itens.append({
            "tipo": "marco_previsto",
            "quando": _dt(m.data_prevista),
            "data": m.data_prevista,
            "titulo": m.titulo,
            "detalhe": "atrasado" if m.atrasado else ("concluído" if m.status == "concluido" else "previsto"),
            "alvo": ("cronogramas.listar", {"orientacao_id": orientacao.id}),
            "marco_id": m.id,
        })
        if m.data_conclusao:
            itens.append({
                "tipo": "marco_concluido",
                "quando": _dt(m.data_conclusao),
                "data": m.data_conclusao,
                "titulo": m.titulo,
                "detalhe": "concluído",
                "alvo": ("cronogramas.listar", {"orientacao_id": orientacao.id}),
                "marco_id": m.id,
            })

    for doc in orientacao.documentos:
        for v in doc.versoes:
            relacionado = f"marco: {doc.marco.titulo}" if doc.marco else ""
            itens.append({
                "tipo": "entrega",
                "quando": _dt(v.enviado_em),
                "data": v.enviado_em,
                "titulo": f"{doc.titulo} (v{v.numero_versao})",
                "detalhe": f"enviado por {v.remetente.nome}",
                "alvo": ("documentos.detalhe",
                         {"orientacao_id": orientacao.id, "documento_id": doc.id}),
                "relacionado": relacionado,
            })

    for p in orientacao.pareceres:
        alvo_txt = ""
        if p.versao_documento:
            alvo_txt = (f"sobre {p.versao_documento.documento.titulo} "
                        f"v{p.versao_documento.numero_versao}")
        itens.append({
            "tipo": "parecer",
            "quando": _dt(p.emitido_em),
            "data": p.emitido_em,
            "titulo": f"Parecer: {RESULTADO_LABEL[p.resultado]}",
            "detalhe": f"por {p.emissor.nome}",
            "alvo": ("atas.listar_pareceres", {"orientacao_id": orientacao.id}),
            "relacionado": alvo_txt,
        })

    for a in orientacao.atas:
        discutidos = ", ".join(m.titulo for m in a.marcos)
        itens.append({
            "tipo": "reuniao",
            "quando": _dt(a.data_reuniao),
            "data": a.data_reuniao,
            "titulo": "Reunião de orientação",
            "detalhe": ("finalizada" if a.status == "finalizada" else "rascunho"),
            "alvo": ("atas.detalhe_ata",
                     {"orientacao_id": orientacao.id, "ata_id": a.id}),
            "relacionado": f"discutiu: {discutidos}" if discutidos else "",
        })

    itens.sort(key=lambda e: e["quando"], reverse=True)
    return itens
