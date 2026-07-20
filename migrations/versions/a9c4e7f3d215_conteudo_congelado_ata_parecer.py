"""Conteúdo impresso congelado em atas finalizadas e pareceres

PDF e hash de integridade passam a derivar de um snapshot canônico gravado na
finalização/emissão, estável a alterações externas posteriores (título do
projeto, nomes). O backfill congela os registros já finalizados/emitidos com o
conteúdo vigente no momento desta migração.

Revision ID: a9c4e7f3d215
Revises: f2b6d81c4a55
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm

revision = "a9c4e7f3d215"
down_revision = "f2b6d81c4a55"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ata", sa.Column("conteudo_congelado", sa.Text(), nullable=True))
    op.add_column("parecer", sa.Column("conteudo_congelado", sa.Text(), nullable=True))

    # backfill com as mesmas funções de congelamento da aplicação, para que o
    # formato seja idêntico ao dos registros futuros
    from app.models import Ata, Parecer
    from app.services.exportacao import congelar_ata, congelar_parecer

    session = orm.Session(bind=op.get_bind())
    for ata in session.query(Ata).filter(Ata.finalizada_em.isnot(None)):
        congelar_ata(ata)
    for parecer in session.query(Parecer):
        congelar_parecer(parecer)
    session.flush()


def downgrade():
    with op.batch_alter_table("parecer") as batch:
        batch.drop_column("conteudo_congelado")
    with op.batch_alter_table("ata") as batch:
        batch.drop_column("conteudo_congelado")
