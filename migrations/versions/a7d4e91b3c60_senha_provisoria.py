"""Senha provisória: marca da senha gerada pelo sistema

A conta criada pelo administrador ou pelo orientador passa a nascer com senha
gerada aleatoriamente e enviada por e-mail. Enquanto a marca estiver de pé, o
acesso fica restrito à tela de troca de senha.

Contas existentes recebem `0` no backfill: nenhuma delas teve a senha gerada
pelo sistema, e marcá-las prenderia todo mundo na tela de troca no primeiro
acesso após a implantação.

Revision ID: a7d4e91b3c60
Revises: f5c1a83d6e24
Create Date: 2026-07-23
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d4e91b3c60"
down_revision = "f5c1a83d6e24"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as batch:
        batch.add_column(
            sa.Column(
                "senha_provisoria",
                sa.Boolean(),
                nullable=False,
                # sa.false() e não sa.text("0"): o literal inteiro vira
                # `DEFAULT 0` numa coluna booleana, que o SQLite aceita e o
                # PostgreSQL recusa. `sa.false()` deixa o dialeto escolher (0
                # aqui, false lá), e o destino de uso institucional é PG.
                server_default=sa.false(),
            )
        )


def downgrade():
    """Reversão sem perda de acesso: some a marca, e quem estava obrigado a
    trocar a senha volta a poder usar a provisória indefinidamente."""
    with op.batch_alter_table("usuario") as batch:
        batch.drop_column("senha_provisoria")
