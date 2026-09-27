"""Versão de documento com arquivo opcional (só comentário)

Uma versão passa a poder ser apenas comentário, sem arquivo anexado — o caso do
retorno cujo conteúdo é todo textual. As quatro colunas de arquivo tornam-se
NULL-áveis; nome_fisico segue unique (SQLite admite múltiplos NULL). Aditiva:
versões existentes têm arquivo e continuam válidas.

Revision ID: c7e1a9d4f062
Revises: b4d7f2e91c63
Create Date: 2026-09-21
"""
import sqlalchemy as sa
from alembic import op

revision = "c7e1a9d4f062"
down_revision = "b4d7f2e91c63"
branch_labels = None
depends_on = None

_COLUNAS = ("nome_original", "nome_fisico", "tamanho_bytes", "mimetype")


def upgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        for coluna in _COLUNAS:
            batch_op.alter_column(coluna, nullable=True)


def downgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        for coluna in _COLUNAS:
            batch_op.alter_column(coluna, nullable=False)
