"""Regras de negócio de atas e pareceres: imutabilidade imposta no serviço."""
from datetime import datetime, timezone

from app.models import Ata
from app.services import auditoria


class AtaImutavel(Exception):
    pass


def atualizar_ata(ata: Ata, *, data_reuniao, pauta, deliberacoes):
    if ata.imutavel:
        auditoria.registrar(
            "tentativa_edicao_ata_finalizada", "ata", ata.id
        )
        raise AtaImutavel("Ata finalizada é imutável.")
    ata.data_reuniao = data_reuniao
    ata.pauta = pauta
    ata.deliberacoes = deliberacoes
    auditoria.registrar("edicao_ata", "ata", ata.id)


def finalizar_ata(ata: Ata):
    if ata.imutavel:
        raise AtaImutavel("Ata já finalizada.")
    ata.status = "finalizada"
    ata.finalizada_em = datetime.now(timezone.utc)
    auditoria.registrar("finalizacao_ata", "ata", ata.id)
