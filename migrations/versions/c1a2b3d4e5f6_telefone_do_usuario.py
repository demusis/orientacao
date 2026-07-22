"""Telefone (celular) opcional do usuario

Revision ID: c1a2b3d4e5f6
Revises: b25557e3b3d2
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a2b3d4e5f6'
down_revision = 'b25557e3b3d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuario') as batch_op:
        batch_op.add_column(sa.Column('telefone', sa.String(length=32), nullable=True))


def downgrade():
    with op.batch_alter_table('usuario') as batch_op:
        batch_op.drop_column('telefone')
