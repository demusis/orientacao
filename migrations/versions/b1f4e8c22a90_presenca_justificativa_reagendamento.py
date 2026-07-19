"""Presença/justificativa por participação, hora da reunião e reagendamentos

Revision ID: b1f4e8c22a90
Revises: 7a3c21b9d0e4
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "b1f4e8c22a90"
down_revision = "7a3c21b9d0e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ata", sa.Column("hora_reuniao", sa.Time(), nullable=True))

    # batch mode: SQLite não aceita ADD COLUMN com FK fora do rebuild
    with op.batch_alter_table("ata_orientacao") as batch:
        batch.add_column(
            sa.Column(
                "presenca",
                sa.Enum("pendente", "presente", "ausente", name="presenca_ata"),
                nullable=False,
                server_default="pendente",
            )
        )
        batch.add_column(
            sa.Column("presenca_registrada_em", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column("presenca_registrada_por", sa.Integer(), nullable=True)
        )
        batch.add_column(sa.Column("justificativa", sa.Text(), nullable=True))
        batch.add_column(sa.Column("justificativa_em", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_ata_orientacao_registrador",
            "usuario",
            ["presenca_registrada_por"],
            ["id"],
        )

    op.create_table(
        "reagendamento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ata_id", sa.Integer(), sa.ForeignKey("ata.id"), nullable=False),
        sa.Column("data_anterior", sa.Date(), nullable=False),
        sa.Column("hora_anterior", sa.Time(), nullable=True),
        sa.Column("data_nova", sa.Date(), nullable=False),
        sa.Column("hora_nova", sa.Time(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "registrado_por", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False
        ),
        sa.Column("registrado_em", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("reagendamento")
    with op.batch_alter_table("ata_orientacao") as batch:
        batch.drop_column("justificativa_em")
        batch.drop_column("justificativa")
        batch.drop_column("presenca_registrada_por")
        batch.drop_column("presenca_registrada_em")
        batch.drop_column("presenca")
    op.drop_column("ata", "hora_reuniao")
