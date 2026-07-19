"""Reuniões individuais e em grupo: ata M:N com orientações e marco.grupo_id

Revision ID: 7a3c21b9d0e4
Revises: 092f0d191451
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "7a3c21b9d0e4"
down_revision = "092f0d191451"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ata_orientacao",
        sa.Column("ata_id", sa.Integer(), sa.ForeignKey("ata.id"), primary_key=True),
        sa.Column(
            "orientacao_id", sa.Integer(), sa.ForeignKey("orientacao.id"), primary_key=True
        ),
    )
    op.add_column(
        "ata",
        sa.Column(
            "tipo",
            sa.Enum("individual", "grupo", name="tipo_ata"),
            nullable=False,
            server_default="individual",
        ),
    )
    op.add_column("ata", sa.Column("orientador_id", sa.Integer(), nullable=True))

    # backfill: associação e convocante derivados do vínculo original
    op.execute(
        "INSERT INTO ata_orientacao (ata_id, orientacao_id) "
        "SELECT id, orientacao_id FROM ata"
    )
    op.execute(
        "UPDATE ata SET orientador_id = ("
        "SELECT orientador_id FROM orientacao WHERE orientacao.id = ata.orientacao_id)"
    )

    with op.batch_alter_table("ata") as batch:
        batch.alter_column("orientador_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_ata_orientador", "usuario", ["orientador_id"], ["id"])
        batch.drop_column("orientacao_id")

    op.add_column("marco", sa.Column("grupo_id", sa.String(length=32), nullable=True))
    op.create_index("ix_marco_grupo_id", "marco", ["grupo_id"])


def downgrade():
    op.drop_index("ix_marco_grupo_id", table_name="marco")
    op.drop_column("marco", "grupo_id")

    op.add_column("ata", sa.Column("orientacao_id", sa.Integer(), nullable=True))
    # atas de grupo colapsam para o primeiro vínculo associado
    op.execute(
        "UPDATE ata SET orientacao_id = ("
        "SELECT MIN(orientacao_id) FROM ata_orientacao WHERE ata_orientacao.ata_id = ata.id)"
    )
    with op.batch_alter_table("ata") as batch:
        batch.alter_column("orientacao_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_ata_orientacao", "orientacao", ["orientacao_id"], ["id"]
        )
        batch.drop_column("orientador_id")
    op.drop_column("ata", "tipo")
    op.drop_table("ata_orientacao")
