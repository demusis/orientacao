"""Realinha o marcador do disparo diário de avisos ao dia local

O portão diário passou a comparar `avisos_enviados_em` com o dia LOCAL
(hoje_local), não mais com o dia UTC. Um valor gravado pelo código antigo na
janela 20h–24h locais é o "amanhã" UTC — e, lido pela regra nova, calaria os
avisos do dia local seguinte inteiro, em silêncio. Anula-se o marcador apenas
quando ele está no futuro do dia local; o registro de quem já recebeu
(`avisos_entregues`) fica intacto e continua evitando mensagem duplicada.

O downgrade não repõe o valor anulado (não há como saber o original); o efeito
é no máximo um disparo a mais no dia.

Revision ID: e7a1c94d20b8
Revises: d6f3a82c15e9
Create Date: 2026-07-26
"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alembic import op

revision = "e7a1c94d20b8"
down_revision = "d6f3a82c15e9"
branch_labels = None
depends_on = None


def upgrade():
    # o fuso padrão do sistema; a migração roda uma vez e o desvio possível é
    # de um dia, então não vale ler a configuração da aplicação aqui
    try:
        hoje = datetime.now(ZoneInfo("America/Cuiaba")).date().isoformat()
    except ZoneInfoNotFoundError:  # ambiente sem base IANA: usa UTC
        hoje = datetime.now(UTC).date().isoformat()
    op.execute(
        "UPDATE configuracao_email SET avisos_enviados_em = NULL "
        f"WHERE avisos_enviados_em > '{hoje}'"
    )


def downgrade():
    pass
