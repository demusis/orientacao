"""Nota de conclusao do marco (nota opcional do orientando ao sinalizar)

Revision ID: e3c4d5f6a7b8
Revises: d2b3c4e5f6a7
Create Date: 2026-07-22 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3c4d5f6a7b8'
down_revision = 'd2b3c4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('marco') as batch_op:
        batch_op.add_column(sa.Column('nota_conclusao', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('marco') as batch_op:
        batch_op.drop_column('nota_conclusao')
