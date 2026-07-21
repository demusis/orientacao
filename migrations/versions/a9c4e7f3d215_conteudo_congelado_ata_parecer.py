"""Conteúdo impresso congelado em atas finalizadas e pareceres

PDF e hash de integridade passam a derivar de um snapshot canônico gravado na
finalização/emissão, estável a alterações externas posteriores (título do
projeto, nomes).

**Correção de 21/07/2026.** Esta migração fazia o backfill importando os modelos
ORM e as funções `congelar_ata`/`congelar_parecer` da aplicação. Migração não
pode depender do código vivo: assim que `Ata` ganhou a coluna `formato`, a
consulta ORM daqui passou a pedir uma coluna que ainda não existe neste ponto da
cadeia, e **uma instalação nova deixou de conseguir subir do zero**. Pior, mesmo
funcionando, `congelar_ata` de hoje produz snapshot diferente do de ontem, de
modo que replicar a migração geraria dados diversos dos que a produção tem.

O backfill foi removido, e sem prejuízo: as colunas nascem nulas e a aplicação
já trata isso — `_dados_vigentes_ata` e `hash_ata` recalculam a partir dos dados
correntes quando não há snapshot. Congelar era estabilização, não requisito de
correção. Instalação nova não tem registro anterior a congelar, e a produção
já aplicou esta revisão com o backfill original.

Revision ID: a9c4e7f3d215
Revises: f2b6d81c4a55
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "a9c4e7f3d215"
down_revision = "f2b6d81c4a55"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ata", sa.Column("conteudo_congelado", sa.Text(), nullable=True))
    op.add_column("parecer", sa.Column("conteudo_congelado", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("parecer") as batch:
        batch.drop_column("conteudo_congelado")
    with op.batch_alter_table("ata") as batch:
        batch.drop_column("conteudo_congelado")
