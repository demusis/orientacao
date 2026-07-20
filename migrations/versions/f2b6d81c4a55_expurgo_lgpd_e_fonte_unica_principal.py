"""Expurgo LGPD das colunas de justificativa e fonte única do orientador principal

Revision ID: f2b6d81c4a55
Revises: e8a5c37d9b12
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "f2b6d81c4a55"
down_revision = "e8a5c37d9b12"
branch_labels = None
depends_on = None


def upgrade():
    # LGPD: elimina colunas E dados de justificativa de ausência
    with op.batch_alter_table("ata_orientacao") as batch:
        batch.drop_column("justificativa_em")
        batch.drop_column("justificativa")

    # o principal tem fonte única em orientacao.orientador_id;
    # a equipe passa a conter apenas coorientadores
    op.execute("DELETE FROM orientacao_orientador WHERE funcao = 'principal'")


def downgrade():
    # os dados expurgados não são recuperáveis (intencional)
    with op.batch_alter_table("ata_orientacao") as batch:
        batch.add_column(sa.Column("justificativa", sa.Text(), nullable=True))
        batch.add_column(sa.Column("justificativa_em", sa.DateTime(), nullable=True))
    op.execute(
        "INSERT INTO orientacao_orientador (orientacao_id, usuario_id, funcao, designado_em) "
        "SELECT id, orientador_id, 'principal', CURRENT_TIMESTAMP FROM orientacao"
    )
