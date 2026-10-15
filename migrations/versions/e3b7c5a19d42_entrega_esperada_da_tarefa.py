"""Tarefa diz o que espera: entrega_esperada, texto-base e data de criação

`entrega_esperada` (documento | revisao | ato, ou NULL = não especificado),
`documento_base_id` (o texto a revisar, sem chave estrangeira para não fechar
ciclo com documento.marco_id) e `criado_em` (NULL nas tarefas existentes).
Aditiva: nenhuma tarefa muda de comportamento.

Revision ID: e3b7c5a19d42
Revises: d9f3a2b61e85
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "e3b7c5a19d42"
down_revision = "d9f3a2b61e85"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marco") as batch_op:
        batch_op.add_column(sa.Column("entrega_esperada", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("documento_base_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("criado_em", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("marco") as batch_op:
        batch_op.drop_column("criado_em")
        batch_op.drop_column("documento_base_id")
        batch_op.drop_column("entrega_esperada")
