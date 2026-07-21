"""Formato de redação dos campos longos de ata e parecer

Distingue o registro redigido ANTES da adoção do markdown daquele redigido
depois. Sem essa marca, `Ata.formato_conteudo` supunha "markdown" para todo
rascunho ainda não congelado, e uma pauta antiga com "# de participantes: 4"
perdia o "#" ao ser exibida — perda que virava permanente ao finalizar a ata,
pois o snapshot passava a declarar markdown.

Nenhuma heurística sobre o conteúdo distinguiria os dois casos com segurança:
"- item" é lista para uns e travessão para outros. Daí a coluna.

O `server_default` de "texto" é o que preenche as linhas existentes, e fica na
tabela de propósito: registro futuro inserido por caminho que não passe pelo ORM
herda o comportamento conservador — literal — em vez de ganhar marcação por
omissão. O padrão "markdown" dos registros novos vem do lado Python, em
`models/ata.py`, e é sempre enviado explicitamente no INSERT.

Revision ID: 07c3c4662e8d
Revises: 50fdafd127f9
Create Date: 2026-07-21
"""
import sqlalchemy as sa
from alembic import op

revision = "07c3c4662e8d"
down_revision = "50fdafd127f9"
branch_labels = None
depends_on = None

FORMATO = sa.Enum("texto", "markdown", name="formato_conteudo")


def upgrade():
    for tabela in ("ata", "parecer"):
        with op.batch_alter_table(tabela, schema=None) as batch:
            batch.add_column(
                sa.Column(
                    "formato",
                    FORMATO,
                    nullable=False,
                    server_default="texto",
                )
            )

    # Registro já congelado carrega o formato dentro do próprio snapshot, que
    # prevalece sobre esta coluna; ainda assim alinha-se os dois, para que a
    # coluna nunca contradiga o documento assinado.
    op.execute(
        "UPDATE ata SET formato = 'markdown' "
        "WHERE conteudo_congelado LIKE '%\"formato\":\"markdown\"%'"
    )
    op.execute(
        "UPDATE parecer SET formato = 'markdown' "
        "WHERE conteudo_congelado LIKE '%\"formato\":\"markdown\"%'"
    )


def downgrade():
    for tabela in ("parecer", "ata"):
        with op.batch_alter_table(tabela, schema=None) as batch:
            batch.drop_column("formato")
