"""Tipo e etapa do marco deixam de se sobrepor

Qualificação, publicação e defesa figuravam nas duas listas de classificação.
Passam a existir apenas como TIPO — são atos datados, não períodos —, e a ETAPA
fica restrita a fases da pesquisa. Nenhum rótulo pertence às duas listas.

O tipo também é reformulado para atender à iniciação científica: entram projeto
de pesquisa e comitê de ética, "relatório anual" vira "relatório" (abrangendo o
parcial e o final) e a proficiência sai, por ser exame institucional alheio ao
processo de orientação.

Revision ID: d7b3f915a6c8
Revises: c5a2e08b71d4
Create Date: 2026-07-21
"""
import sqlalchemy as sa
from alembic import op

revision = "d7b3f915a6c8"
down_revision = "c5a2e08b71d4"
branch_labels = None
depends_on = None

TIPOS_NOVOS = (
    "outro",
    "projeto",
    "comite_etica",
    "qualificacao",
    "relatorio",
    "publicacao",
    "defesa",
)
TIPOS_ANTIGOS = (
    "outro",
    "qualificacao",
    "defesa",
    "relatorio_anual",
    "proficiencia",
    "publicacao",
)

# As três etapas suprimidas (30 qualificação, 70 publicação, 80 defesa) migram
# para a fase adjacente, e não para 0 ("Não classificada"): recolhê-las a 0 faria
# uma defesa saltar para o topo do cronograma. O ato em si é preservado no tipo,
# mas só quando este estava em "outro" — escolha explícita não é sobrescrita.
REMAPA_ETAPA = """
UPDATE marco SET etapa = CASE etapa
    WHEN 30 THEN 20
    WHEN 40 THEN 30
    WHEN 50 THEN 40
    WHEN 60 THEN 50
    WHEN 70 THEN 50
    WHEN 80 THEN 60
    ELSE etapa
END
"""


def upgrade():
    # sa.Enum tem create_constraint=False por padrão desde o SQLAlchemy 1.4: a
    # coluna é um VARCHAR sem CHECK, e o banco aceitaria qualquer texto. A
    # tipologia é imposta apenas pelo SelectField do formulário. O alargamento
    # para String(30) abaixo é, portanto, precaução e não necessidade — o que
    # importa de fato é o remapeamento dos valores, sem o qual sobrariam linhas
    # com um tipo que nenhuma tela sabe mais rotular.
    with op.batch_alter_table("marco") as batch:
        batch.alter_column(
            "tipo", type_=sa.String(30), existing_type=sa.Enum(*TIPOS_ANTIGOS)
        )

    # a etapa depende do tipo antigo para decidir se o preenche; roda primeiro
    op.execute(
        "UPDATE marco SET tipo = 'qualificacao' WHERE etapa = 30 AND tipo = 'outro'"
    )
    op.execute(
        "UPDATE marco SET tipo = 'publicacao' WHERE etapa = 70 AND tipo = 'outro'"
    )
    op.execute("UPDATE marco SET tipo = 'defesa' WHERE etapa = 80 AND tipo = 'outro'")
    op.execute(REMAPA_ETAPA)

    op.execute("UPDATE marco SET tipo = 'relatorio' WHERE tipo = 'relatorio_anual'")
    # a proficiência sai da tipologia; sem esta linha o marco legado ficaria com
    # um tipo ausente de TIPO_MARCO_LABEL e a listagem quebraria com KeyError
    op.execute("UPDATE marco SET tipo = 'outro' WHERE tipo = 'proficiencia'")

    with op.batch_alter_table("marco") as batch:
        batch.alter_column(
            "tipo",
            type_=sa.Enum(*TIPOS_NOVOS, name="tipo_marco"),
            existing_type=sa.String(30),
        )


def downgrade():
    """Reversão lesiva: projeto e comitê de ética não têm correspondente na
    tipologia antiga e são rebaixados a "outro"; a etapa volta aos códigos
    antigos, mas as três etapas de ato não são reconstituídas, pois já não se
    distingue o marco que as tinha daquele que sempre esteve na fase vizinha.
    Mesmo critério de f2b6d81c4a55 e b3f1a86d5c47."""
    with op.batch_alter_table("marco") as batch:
        batch.alter_column(
            "tipo", type_=sa.String(30), existing_type=sa.Enum(*TIPOS_NOVOS)
        )

    op.execute("UPDATE marco SET tipo = 'relatorio_anual' WHERE tipo = 'relatorio'")
    op.execute("UPDATE marco SET tipo = 'outro' WHERE tipo IN ('projeto', 'comite_etica')")

    op.execute(
        """
        UPDATE marco SET etapa = CASE etapa
            WHEN 60 THEN 80
            WHEN 50 THEN 60
            WHEN 40 THEN 50
            WHEN 30 THEN 40
            ELSE etapa
        END
        """
    )

    with op.batch_alter_table("marco") as batch:
        batch.alter_column(
            "tipo",
            type_=sa.Enum(*TIPOS_ANTIGOS, name="tipo_marco"),
            existing_type=sa.String(30),
        )
