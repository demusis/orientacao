"""Registro do último acesso do usuário

Habilita a medição agregada de adesão (contas nunca acessadas, contas ociosas)
no ciclo periódico de avaliação. Sem backfill: nulo significa "não acessou desde
a instrumentação", que é o que de fato se sabe.

Revision ID: c5a2e08b71d4
Revises: b3f1a86d5c47
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "c5a2e08b71d4"
down_revision = "b3f1a86d5c47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("ultimo_acesso", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("usuario") as batch:
        batch.drop_column("ultimo_acesso")
