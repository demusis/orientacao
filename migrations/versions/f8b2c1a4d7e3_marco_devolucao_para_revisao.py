"""Devolução de marco para revisão (devolvido_em + nota_devolucao)

Dá ao ciclo do marco a volta que faltava: o orientador devolve a entrega para o
orientando corrigir. `devolvido_em` marca a última devolução (e distingue
"devolvido, aguardando o aluno" de "nunca iniciado"); `nota_devolucao` guarda o
que o orientador pediu para corrigir. Ambos nullable — aditivo, sem backfill.

Revision ID: f8b2c1a4d7e3
Revises: e7a1c94d20b8
Create Date: 2026-07-26
"""
import sqlalchemy as sa
from alembic import op

revision = "f8b2c1a4d7e3"
down_revision = "e7a1c94d20b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marco") as batch_op:
        batch_op.add_column(sa.Column("devolvido_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("nota_devolucao", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("marco") as batch_op:
        batch_op.drop_column("nota_devolucao")
        batch_op.drop_column("devolvido_em")
