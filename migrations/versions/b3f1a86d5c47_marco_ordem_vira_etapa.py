"""A ordem numérica livre do marco passa a ser a etapa do projeto

A coluna deixa de representar uma posição arbitrária digitada pelo orientador e
passa a representar a fase da pesquisa, escolhida em lista fechada. Os códigos
são espaçados de 10 (ver ETAPAS_MARCO); os valores legados, que não pertencem a
esse conjunto, são recolhidos para 0 ("Não classificada").

Revision ID: b3f1a86d5c47
Revises: a9c4e7f3d215
Create Date: 2026-07-20
"""
from alembic import op

revision = "b3f1a86d5c47"
down_revision = "a9c4e7f3d215"
branch_labels = None
depends_on = None

ETAPAS_VALIDAS = "(0,10,20,30,40,50,60,70,80)"


def upgrade():
    # batch mode: SQLite não renomeia coluna sem rebuild da tabela
    with op.batch_alter_table("marco") as batch:
        batch.alter_column("ordem", new_column_name="etapa")
    op.execute(f"UPDATE marco SET etapa = 0 WHERE etapa NOT IN {ETAPAS_VALIDAS}")


def downgrade():
    # a normalização não é revertida: os números originais não são recuperáveis
    # (mesmo critério adotado em f2b6d81c4a55)
    with op.batch_alter_table("marco") as batch:
        batch.alter_column("etapa", new_column_name="ordem")
