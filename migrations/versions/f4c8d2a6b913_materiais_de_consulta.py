"""Materiais de consulta compartilhados com orientandos

Tabelas novas `material`, `material_orientacao` (com quem é compartilhado) e
`material_marco` (tarefas onde aparece). Aditiva.

Revision ID: f4c8d2a6b913
Revises: e3b7c5a19d42
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "f4c8d2a6b913"
down_revision = "e3b7c5a19d42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "material",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("nome_original", sa.String(length=255), nullable=False),
        sa.Column("nome_fisico", sa.String(length=64), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=False),
        sa.Column("enviado_por", sa.Integer(), nullable=False),
        sa.Column("enviado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enviado_por"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome_fisico"),
    )
    op.create_table(
        "material_orientacao",
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("orientacao_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"]),
        sa.ForeignKeyConstraint(["orientacao_id"], ["orientacao.id"]),
        sa.PrimaryKeyConstraint("material_id", "orientacao_id"),
    )
    op.create_table(
        "material_marco",
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("marco_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"]),
        sa.ForeignKeyConstraint(["marco_id"], ["marco.id"]),
        sa.PrimaryKeyConstraint("material_id", "marco_id"),
    )


def downgrade():
    op.drop_table("material_marco")
    op.drop_table("material_orientacao")
    op.drop_table("material")
