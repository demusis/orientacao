"""Coorientação: equipe de orientação por vínculo

Revision ID: e8a5c37d9b12
Revises: d4e9b12c8f01
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "e8a5c37d9b12"
down_revision = "d4e9b12c8f01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "orientacao_orientador",
        sa.Column(
            "orientacao_id", sa.Integer(), sa.ForeignKey("orientacao.id"), primary_key=True
        ),
        sa.Column(
            "usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), primary_key=True
        ),
        sa.Column(
            "funcao",
            sa.Enum("principal", "coorientador", name="funcao_orientador"),
            nullable=False,
            server_default="coorientador",
        ),
        sa.Column("designado_em", sa.DateTime(), nullable=False),
    )
    # backfill: orientador atual torna-se principal na equipe
    op.execute(
        "INSERT INTO orientacao_orientador (orientacao_id, usuario_id, funcao, designado_em) "
        "SELECT id, orientador_id, 'principal', CURRENT_TIMESTAMP FROM orientacao"
    )


def downgrade():
    op.drop_table("orientacao_orientador")
