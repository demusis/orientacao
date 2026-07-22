"""Modelo de documento (acervo global de arquivos-modelo)

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-22 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2b3c4e5f6a7'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'modelo_documento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=255), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('nome_original', sa.String(length=255), nullable=False),
        sa.Column('nome_fisico', sa.String(length=64), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('mimetype', sa.String(length=100), nullable=False),
        sa.Column('enviado_por', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['enviado_por'], ['usuario.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome_fisico'),
    )


def downgrade():
    op.drop_table('modelo_documento')
