"""Parâmetros configuráveis do sinal de risco do prazo

Linha única (id=1), criada quando o administrador salva a tela "Prazo e risco".
A ausência da linha significa os padrões (amarelo acima de 75%, vermelho acima
de 90%, críticos qualificação e defesa) — por isso não há dado a semear.

O downgrade descarta os parâmetros escolhidos; o sistema volta aos padrões.

Revision ID: d6f3a82c15e9
Revises: b9e2f47a1c85
Create Date: 2026-07-25
"""
import sqlalchemy as sa
from alembic import op

revision = "d6f3a82c15e9"
down_revision = "b9e2f47a1c85"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "configuracao_risco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("limiar_medio", sa.Integer(), nullable=False),
        sa.Column("limiar_alto", sa.Integer(), nullable=False),
        sa.Column("tipos_criticos", sa.Text(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
        sa.Column("atualizado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["atualizado_por"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("configuracao_risco")
