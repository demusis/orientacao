"""Instante corrente em UTC ingênuo.

O banco grava datas e horas sem fuso (colunas `DateTime` recebem
`datetime.now(timezone.utc)`, cujo `tzinfo` é descartado na gravação). Comparar
com um valor *aware* dispararia `TypeError` no SQLite; daí um ponto único que
devolve sempre a mesma forma ingênua."""
from datetime import UTC, datetime


def agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
