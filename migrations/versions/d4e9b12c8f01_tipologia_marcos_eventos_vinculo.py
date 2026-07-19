"""Tipologia de marcos e eventos formais do vínculo

Revision ID: d4e9b12c8f01
Revises: c7d2a94f1b33
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e9b12c8f01"
down_revision = "c7d2a94f1b33"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marco",
        sa.Column(
            "tipo",
            sa.Enum(
                "outro",
                "qualificacao",
                "defesa",
                "relatorio_anual",
                "proficiencia",
                "publicacao",
                name="tipo_marco",
            ),
            nullable=False,
            server_default="outro",
        ),
    )
    op.create_table(
        "evento_vinculo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "orientacao_id", sa.Integer(), sa.ForeignKey("orientacao.id"), nullable=False
        ),
        sa.Column(
            "tipo",
            sa.Enum(
                "prorrogacao",
                "trancamento",
                "destrancamento",
                "mudanca_titulo",
                name="tipo_evento",
            ),
            nullable=False,
        ),
        sa.Column("fundamentacao", sa.Text(), nullable=False),
        sa.Column("data_anterior", sa.Date(), nullable=True),
        sa.Column("data_nova", sa.Date(), nullable=True),
        sa.Column("texto_anterior", sa.String(length=255), nullable=True),
        sa.Column("texto_novo", sa.String(length=255), nullable=True),
        sa.Column(
            "registrado_por", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False
        ),
        sa.Column("registrado_em", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("evento_vinculo")
    op.drop_column("marco", "tipo")
