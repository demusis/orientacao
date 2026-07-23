"""Cancelamento de reunião agendada

Acrescenta à ata o registro do cancelamento: quando, por quem e por quê. A
reunião marcada que não vai ocorrer deixa de ser apagada ou deixada na agenda
como rascunho eterno.

O estado "cancelada" em si não exige DDL. `sa.Enum` tem create_constraint=False
desde o SQLAlchemy 1.4, de modo que `ata.status` já é um VARCHAR sem CHECK, e o
valor novo é imposto apenas pelo modelo e pelos formulários. O mesmo raciocínio
está registrado em d7b3f915a6c8.

Revision ID: f5c1a83d6e24
Revises: e3c4d5f6a7b8
Create Date: 2026-07-23
"""
import sqlalchemy as sa
from alembic import op

revision = "f5c1a83d6e24"
down_revision = "e3c4d5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ata") as batch:
        batch.add_column(sa.Column("cancelada_em", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancelada_por", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("motivo_cancelamento", sa.Text(), nullable=True))
        # a chave nomeada é o que permite ao batch_alter_table do SQLite
        # reconstruir a tabela na reversão sem deixar restrição órfã
        batch.create_foreign_key(
            "fk_ata_cancelada_por_usuario", "usuario", ["cancelada_por"], ["id"]
        )


def downgrade():
    """Reversão lesiva: a reunião cancelada volta a rascunho e reaparece na
    agenda e nos lembretes, perdidos o motivo, o autor e a data do cancelamento.
    Não há como distingui-la de uma reunião que segue marcada. Mesmo critério
    declarado em f2b6d81c4a55 e d7b3f915a6c8."""
    op.execute("UPDATE ata SET status = 'rascunho' WHERE status = 'cancelada'")
    with op.batch_alter_table("ata") as batch:
        batch.drop_constraint("fk_ata_cancelada_por_usuario", type_="foreignkey")
        batch.drop_column("motivo_cancelamento")
        batch.drop_column("cancelada_por")
        batch.drop_column("cancelada_em")
