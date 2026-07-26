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
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import current_app


def agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def agora_local() -> datetime:
    """Hora de parede da instituição, ingênua, para comparar com data/hora de
    reunião. Fora de contexto de aplicação (improvável), cai em UTC."""
    try:
        fuso = ZoneInfo(current_app.config.get("FUSO_LOCAL", "America/Cuiaba"))
    except RuntimeError:  # sem app context
        return agora()
    return datetime.now(fuso).replace(tzinfo=None)
