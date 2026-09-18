"""Versão de documento como devolução (eh_devolucao)

Marca uma versão enviada pelo orientador como devolução com correções — não é
entrega a avaliar. Fica fora de "aguardando parecer" e devolve a tarefa. Coluna
booleana, default False; aditiva, sem backfill.

Revision ID: a1c9e4b782f6
Revises: f8b2c1a4d7e3
Create Date: 2026-07-26
"""
import sqlalchemy as sa
from alembic import op

revision = "a1c9e4b782f6"
down_revision = "f8b2c1a4d7e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        batch_op.add_column(
            sa.Column(
                "eh_devolucao",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        batch_op.drop_column("eh_devolucao")
