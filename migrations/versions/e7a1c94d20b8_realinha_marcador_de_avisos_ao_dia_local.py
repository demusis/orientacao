"""Realinha os marcadores do disparo diário de avisos ao dia local

O portão diário passou a comparar com o dia LOCAL (hoje_local), não mais com o
dia UTC. Dois resíduos do relógio antigo precisam de acerto:

- `avisos_enviados_em` gravado na janela 20h–24h locais é o "amanhã" UTC — e,
  lido pela regra nova, calaria os avisos de um dia local inteiro. Anula-se o
  marcador de hoje ou do futuro (`>=`, não `>`: o gravado ontem à noite vale
  exatamente "hoje" e produziria o mesmo silêncio).
- `avisos_entregues` traz um dia gravado pelo mesmo relógio antigo; quando
  futuro, é realinhado ao dia local COM a lista de e-mails preservada — é ela
  que impede que a reavaliação do portão reenvie o lote a quem já recebeu.

Anular o marcador de um envio legítimo de hoje é inócuo: a reavaliação
encontra todos os destinatários no registro de entregues e nada reenvia.

O downgrade não repõe valores (não há como saber os originais); o efeito
máximo é uma reavaliação a mais, sem duplicatas.

Revision ID: e7a1c94d20b8
Revises: d6f3a82c15e9
Create Date: 2026-07-26
"""
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from alembic import op

revision = "e7a1c94d20b8"
down_revision = "d6f3a82c15e9"
branch_labels = None
depends_on = None


def _hoje_local() -> str:
    # o fuso padrão do sistema; a migração roda uma vez e o desvio possível é
    # de um dia, então não vale ler a configuração da aplicação aqui
    try:
        return datetime.now(ZoneInfo("America/Cuiaba")).date().isoformat()
    except ZoneInfoNotFoundError:  # ambiente sem base IANA: usa UTC
        return datetime.now(UTC).date().isoformat()


def upgrade():
    hoje = _hoje_local()
    ligacao = op.get_bind()
    ligacao.execute(
        sa.text(
            "UPDATE configuracao_email SET avisos_enviados_em = NULL "
            "WHERE avisos_enviados_em >= :hoje"
        ),
        {"hoje": hoje},
    )
    bruto = ligacao.execute(
        sa.text("SELECT avisos_entregues FROM configuracao_email WHERE id = 1")
    ).scalar()
    if bruto:
        try:
            guardado = json.loads(bruto)
        except ValueError:
            guardado = None
        if isinstance(guardado, dict) and guardado.get("dia", "") > hoje:
            guardado["dia"] = hoje
            ligacao.execute(
                sa.text(
                    "UPDATE configuracao_email SET avisos_entregues = :novo "
                    "WHERE id = 1"
                ),
                {"novo": json.dumps(guardado, ensure_ascii=False)},
            )


def downgrade():
    pass
