"""Regras de negócio de atas: imutabilidade, reagendamento e presenças.
Todos os eventos recebem carimbo de data/hora (UTC) e registro em auditoria."""
from datetime import datetime, timezone

from app.extensions import db
from app.models import Ata, AtaParticipacao, Reagendamento
from app.services import auditoria


class AtaImutavel(Exception):
    pass


class OperacaoInvalida(Exception):
    pass


def atualizar_ata(ata: Ata, *, pauta, deliberacoes):
    """Edição de conteúdo do rascunho. Data/hora da reunião mudam apenas via
    reagendar_ata, para que toda alteração de agenda deixe registro próprio."""
    if ata.imutavel:
        auditoria.registrar("tentativa_edicao_ata_finalizada", "ata", ata.id)
        raise AtaImutavel("Ata finalizada é imutável.")
    ata.pauta = pauta
    ata.deliberacoes = deliberacoes
    auditoria.registrar("edicao_ata", "ata", ata.id)


def finalizar_ata(ata: Ata):
    if ata.imutavel:
        raise AtaImutavel("Ata já finalizada.")
    ata.status = "finalizada"
    ata.finalizada_em = datetime.now(timezone.utc)
    auditoria.registrar("finalizacao_ata", "ata", ata.id)


def reagendar_ata(ata: Ata, usuario, *, data_nova, hora_nova, motivo=None):
    if ata.imutavel:
        auditoria.registrar("tentativa_reagendamento_ata_finalizada", "ata", ata.id)
        raise AtaImutavel("Reunião com ata finalizada não pode ser reagendada.")
    registro = Reagendamento(
        ata_id=ata.id,
        data_anterior=ata.data_reuniao,
        hora_anterior=ata.hora_reuniao,
        data_nova=data_nova,
        hora_nova=hora_nova,
        motivo=motivo,
        registrado_por=usuario.id,
    )
    db.session.add(registro)
    ata.data_reuniao = data_nova
    ata.hora_reuniao = hora_nova
    auditoria.registrar(
        "reagendamento_reuniao",
        "ata",
        ata.id,
        {
            "de": f"{registro.data_anterior} {registro.hora_anterior or ''}".strip(),
            "para": f"{data_nova} {hora_nova or ''}".strip(),
            "motivo": motivo,
        },
    )
    return registro


def registrar_presenca(participacao: AtaParticipacao, presenca: str, usuario):
    if presenca not in ("presente", "ausente"):
        raise OperacaoInvalida("Valor de presença inválido.")
    if participacao.ata.imutavel:
        auditoria.registrar(
            "tentativa_presenca_ata_finalizada", "ata", participacao.ata_id
        )
        raise AtaImutavel("Presenças não podem ser alteradas após a finalização da ata.")
    participacao.presenca = presenca
    participacao.presenca_registrada_em = datetime.now(timezone.utc)
    participacao.presenca_registrada_por = usuario.id
    auditoria.registrar(
        "registro_presenca",
        "ata",
        participacao.ata_id,
        {"orientacao_id": participacao.orientacao_id, "presenca": presenca},
    )


def justificar_ausencia(participacao: AtaParticipacao, texto: str):
    """Facultativa; admitida também após a finalização da ata, pois integra a
    participação, não o texto da ata."""
    if participacao.presenca != "ausente":
        raise OperacaoInvalida("Justificativa aplica-se apenas a ausência registrada.")
    participacao.justificativa = texto
    participacao.justificativa_em = datetime.now(timezone.utc)
    auditoria.registrar(
        "justificativa_ausencia",
        "ata",
        participacao.ata_id,
        {"orientacao_id": participacao.orientacao_id},
    )
