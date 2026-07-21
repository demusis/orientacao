"""Evento formal do vínculo: registro fundamentado de uma alteração, com o valor
anterior preservado.

Restou apenas a mudança de título. Prorrogação, trancamento e destrancamento
foram removidos por registrarem decisões que o sistema depois ignorava: o
trancamento não impedia nada nem suspendia a contagem de atraso, e a prorrogação
concorria com o ajuste de datas do administrador, que hoje exige fundamentação e
faz o mesmo. Os três valores continuam em TIPOS_EVENTO para que os registros já
gravados sigam legíveis — o que se deixou de fazer foi produzi-los.
"""
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
    texto_novo: str | None = None,
) -> EventoVinculo:
    if tipo != "mudanca_titulo":
        raise EventoInvalido("Tipo de evento desconhecido.")
    if not texto_novo:
        raise EventoInvalido("Mudança de título exige o novo título.")

    evento = EventoVinculo(
        orientacao_id=orientacao.id,
        tipo=tipo,
        fundamentacao=fundamentacao,
        registrado_por=usuario.id,
        texto_anterior=orientacao.titulo_projeto,
        texto_novo=texto_novo,
    )
    orientacao.titulo_projeto = texto_novo

    db.session.add(evento)
    db.session.flush()
    auditoria.registrar(
        "evento_vinculo",
        "orientacao",
        orientacao.id,
        {"tipo": tipo, "evento_id": evento.id},
    )
    return evento
