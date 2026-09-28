"""Anexos da versão de documento (vários arquivos numa entrega)

Uma versão passa a poder levar, além do arquivo principal (que continua nas
colunas de `versao_documento`), arquivos adicionais: planilha de dados, figuras,
carta de encaminhamento. Aditiva: nenhuma coluna existente muda, e as versões
já gravadas seguem válidas, sem anexos.

Revision ID: d9f3a2b61e85
Revises: c7e1a9d4f062
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "d9f3a2b61e85"
down_revision = "c7e1a9d4f062"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anexo_versao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("versao_id", sa.Integer(), nullable=False),
        sa.Column("nome_original", sa.String(length=255), nullable=False),
        sa.Column("nome_fisico", sa.String(length=64), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["versao_id"], ["versao_documento.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome_fisico"),
    )


def downgrade():
    op.drop_table("anexo_versao")
