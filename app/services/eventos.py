"""Eventos formais do vínculo: prorrogação, trancamento, destrancamento e
mudança de título — com fundamentação obrigatória, preservação do histórico e
aplicação imediata do efeito sobre o vínculo."""
from app.extensions import db
from app.models import EventoVinculo, Orientacao
from app.services import auditoria


class EventoInvalido(Exception):
    pass


def registrar_evento(
    orientacao: Orientacao,
    *,
    tipo: str,
    fundamentacao: str,
    usuario,
    data_nova=None,
    texto_novo: str | None = None,
) -> EventoVinculo:
    evento = EventoVinculo(
        orientacao_id=orientacao.id,
        tipo=tipo,
        fundamentacao=fundamentacao,
        registrado_por=usuario.id,
    )

    if tipo == "prorrogacao":
        if orientacao.status != "ativa":
            raise EventoInvalido("Prorrogação aplica-se apenas a vínculo ativo.")
        if data_nova is None:
            raise EventoInvalido("Prorrogação exige o novo fim previsto.")
        # sem fim previsto anterior, a referência de posterioridade é o início
        referencia = orientacao.data_fim_prevista or orientacao.data_inicio
        if data_nova <= referencia:
            raise EventoInvalido(
                "O novo fim previsto deve ser posterior ao fim vigente "
                "(ou ao início do vínculo, quando não há fim previsto)."
            )
        evento.data_anterior = orientacao.data_fim_prevista
        evento.data_nova = data_nova
        orientacao.data_fim_prevista = data_nova
    elif tipo == "trancamento":
        if orientacao.status != "ativa":
            raise EventoInvalido("Trancamento aplica-se apenas a vínculo ativo.")
        orientacao.status = "suspensa"
    elif tipo == "destrancamento":
        if orientacao.status != "suspensa":
            raise EventoInvalido("Destrancamento aplica-se apenas a vínculo suspenso.")
        orientacao.status = "ativa"
    elif tipo == "mudanca_titulo":
        if not texto_novo:
            raise EventoInvalido("Mudança de título exige o novo título.")
        evento.texto_anterior = orientacao.titulo_projeto
        evento.texto_novo = texto_novo
        orientacao.titulo_projeto = texto_novo
    else:
        raise EventoInvalido("Tipo de evento desconhecido.")

    db.session.add(evento)
    db.session.flush()
    auditoria.registrar(
        "evento_vinculo",
        "orientacao",
        orientacao.id,
        {"tipo": tipo, "evento_id": evento.id},
    )
    return evento
