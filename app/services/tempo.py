"""Instante corrente, nas duas referências que o sistema usa.

`agora()` — UTC ingênuo. O banco grava carimbos sem fuso (colunas `DateTime`
recebem `datetime.now(timezone.utc)`, cujo `tzinfo` é descartado na gravação).
Comparar com um valor *aware* dispararia `TypeError` no SQLite; daí um ponto
único que devolve sempre a mesma forma ingênua.

`agora_local()` — hora de parede no fuso da instituição (`FUSO_LOCAL` na
configuração). Data e hora de **reunião** são digitadas pelo usuário no fuso
dele, não em UTC; toda comparação desses campos com o relógio deve usar esta
referência, senão a reunião de hoje às 08:00 "passa" às 04:00 locais (08:00
UTC) e o dia vira às 20:00. Carimbos de auditoria e afins seguem em `agora()`.
"""
from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app


def agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@lru_cache(maxsize=4)
def _fuso(nome: str) -> ZoneInfo | None:
    """None para nome fora da base IANA — o chamador decide o fallback. Cacheado
    porque a resolução lê arquivo, e isto roda a cada comparação de data."""
    try:
        return ZoneInfo(nome)
    except ZoneInfoNotFoundError:
        return None


def agora_local() -> datetime:
    """Hora de parede da instituição, ingênua, para comparar com data e hora
    digitadas pelo usuário (reuniões, prazos de marco).

    Degrada para UTC — nunca levanta: fora de contexto de aplicação, ou com
    `FUSO_LOCAL` fora da base IANA (um typo no .env derrubaria todo o módulo de
    reuniões com erro 500; prefere-se o relógio errado ao sistema fora do ar,
    com aviso no log)."""
    try:
        nome = current_app.config.get("FUSO_LOCAL", "America/Cuiaba")
    except RuntimeError:  # sem app context
        return agora()
    fuso = _fuso(nome)
    if fuso is None:
        current_app.logger.warning(
            "FUSO_LOCAL inválido (%r): não está na base IANA. Usando UTC.", nome
        )
        return agora()
    return datetime.now(fuso).replace(tzinfo=None)


def hoje_local() -> date:
    """Data de parede da instituição. É com ela que se compara TODA data
    digitada pelo usuário (data de reunião, prazo de marco): comparar com a
    data UTC vira o dia às 20:00 locais e dá por vencido o que ainda vale."""
    return agora_local().date()
