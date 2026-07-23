"""Link da reunião online

Endereço facultativo da sala virtual, informado no agendamento e repetido no
aviso enviado aos convidados. Reunião presencial simplesmente não o preenche.

Revision ID: b9e2f47a1c85
Revises: a7d4e91b3c60
Create Date: 2026-07-23
"""
import sqlalchemy as sa
from alembic import op

revision = "b9e2f47a1c85"
down_revision = "a7d4e91b3c60"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ata") as batch:
        batch.add_column(sa.Column("link_reuniao", sa.String(length=500), nullable=True))


def downgrade():
    """Reversão com perda: os endereços de sala virtual já cadastrados somem, e
    as reuniões futuras passam a não ter onde informá-los."""
    with op.batch_alter_table("ata") as batch:
        batch.drop_column("link_reuniao")
