"""Versão registrada em nome do orientando (em_nome_do_orientando)

O orientador às vezes sobe o arquivo que a orientanda lhe mandou por outro
canal. Marcada assim, a versão conta como entrega DELA — pede parecer, como se
ela mesma tivesse enviado —, ao contrário do upload comum do orientador, que
não cobra parecer dele próprio. Coluna booleana, default False; aditiva.

Revision ID: b4d7f2e91c63
Revises: a1c9e4b782f6
Create Date: 2026-07-26
"""
import sqlalchemy as sa
from alembic import op

revision = "b4d7f2e91c63"
down_revision = "a1c9e4b782f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        batch_op.add_column(
            sa.Column(
                "em_nome_do_orientando",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade():
    with op.batch_alter_table("versao_documento") as batch_op:
        batch_op.drop_column("em_nome_do_orientando")
