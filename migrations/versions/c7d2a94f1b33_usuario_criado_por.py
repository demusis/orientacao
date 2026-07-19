"""usuario.criado_por: autor da criação da conta

Revision ID: c7d2a94f1b33
Revises: b1f4e8c22a90
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d2a94f1b33"
down_revision = "b1f4e8c22a90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as batch:
        batch.add_column(sa.Column("criado_por", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_usuario_criado_por", "usuario", ["criado_por"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("usuario") as batch:
        batch.drop_constraint("fk_usuario_criado_por", type_="foreignkey")
        batch.drop_column("criado_por")
