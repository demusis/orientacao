"""Migração d7b3f915a6c8 — tipo e etapa do marco deixam de se sobrepor.

A produção tem poucos marcos, mas eles são reais: o remapeamento precisa ser
conferido antes de rodar lá. Estes testes executam o Alembic de verdade sobre um
banco temporário, e não uma reimplementação da regra em Python — o que se quer
verificar é a migração, não uma cópia dela.
"""
import os
import sqlite3
import tempfile

import pytest

REVISAO_ANTERIOR = "c5a2e08b71d4"
REVISAO = "d7b3f915a6c8"

# (titulo, tipo, etapa) antes  ->  (tipo, etapa) depois
CASOS = [
    ("defesa sem tipo", "outro", 80, ("defesa", 60)),
    ("defesa com tipo próprio", "relatorio_anual", 80, ("relatorio", 60)),
    ("qualificação sem tipo", "outro", 30, ("qualificacao", 20)),
    ("publicação sem tipo", "outro", 70, ("publicacao", 50)),
    ("proficiência descontinuada", "proficiencia", 10, ("outro", 10)),
    ("redação", "outro", 60, ("outro", 50)),
    ("coleta", "outro", 40, ("outro", 30)),
    ("não classificada", "outro", 0, ("outro", 0)),
]


@pytest.fixture
def banco_migrado():
    """Sobe um banco até a revisão anterior, semeia marcos legados e devolve o
    caminho junto de uma função que aplica a migração em teste."""
    from flask_migrate import upgrade

    from config import TestingConfig

    fd, caminho = tempfile.mkstemp(suffix=".sqlite", prefix="ariadne-migracao-")
    os.close(fd)
    uri_original = TestingConfig.SQLALCHEMY_DATABASE_URI
    # o engine é construído dentro de create_app; alterar depois não teria efeito
    TestingConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{caminho}"
    try:
        from app import create_app

        app = create_app("testing")
        with app.app_context():
            upgrade(revision=REVISAO_ANTERIOR)

            con = sqlite3.connect(caminho)
            con.executemany(
                "INSERT INTO marco (orientacao_id, titulo, data_prevista, status,"
                " tipo, etapa, conclusao_sinalizada) VALUES (1, ?, '2026-09-30',"
                " 'pendente', ?, ?, 0)",
                [(titulo, tipo, etapa) for titulo, tipo, etapa, _ in CASOS],
            )
            con.commit()
            con.close()

            yield caminho, lambda alvo: upgrade(revision=alvo)
    finally:
        TestingConfig.SQLALCHEMY_DATABASE_URI = uri_original
        try:
            os.unlink(caminho)
        except OSError:
            pass


def _marcos(caminho):
    con = sqlite3.connect(caminho)
    linhas = dict(
        (titulo, (tipo, etapa))
        for titulo, tipo, etapa in con.execute(
            "SELECT titulo, tipo, etapa FROM marco"
        )
    )
    con.close()
    return linhas


def test_remapeamento_de_tipo_e_etapa(banco_migrado):
    caminho, aplicar = banco_migrado
    aplicar(REVISAO)

    obtido = _marcos(caminho)
    esperado = {titulo: destino for titulo, _, _, destino in CASOS}
    assert obtido == esperado


def test_tipo_explicito_nao_e_sobrescrito_pela_etapa(banco_migrado):
    """O ato só preenche o tipo deixado em 'outro'. O marco de relatório
    agendado para a etapa de defesa continua sendo um relatório."""
    caminho, aplicar = banco_migrado
    aplicar(REVISAO)

    assert _marcos(caminho)["defesa com tipo próprio"] == ("relatorio", 60)


def test_etapas_suprimidas_nao_sobrevivem(banco_migrado):
    """Nenhuma linha permanece nos códigos 70 e 80, que deixaram de existir."""
    caminho, aplicar = banco_migrado
    aplicar(REVISAO)

    assert not {e for _, e in _marcos(caminho).values()} & {70, 80}


def test_nenhum_tipo_fora_da_tipologia_vigente_sobrevive(banco_migrado):
    """Todo marco termina com um tipo que TIPO_MARCO_LABEL sabe rotular.

    O banco não ajuda aqui: sa.Enum tem create_constraint=False por padrão desde
    o SQLAlchemy 1.4, de modo que `tipo` é um VARCHAR sem CHECK e aceitaria
    qualquer texto — a tipologia é imposta só pelo SelectField do formulário.
    Como não há rede de proteção no esquema, o remapeamento da migração é a
    única coisa que impede um KeyError na listagem, e é o que se afere aqui."""
    from app.models.cronograma import TIPO_MARCO_LABEL

    caminho, aplicar = banco_migrado
    aplicar(REVISAO)

    tipos = {tipo for tipo, _ in _marcos(caminho).values()}
    assert tipos <= set(TIPO_MARCO_LABEL)
