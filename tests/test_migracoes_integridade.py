"""Integridade da cadeia de migrações.

Estes testes existem por causa de um defeito real: a revisão a9c4e7f3d215
importava os modelos ORM da aplicação para fazer backfill. Quando `Ata` ganhou a
coluna `formato`, aquela consulta passou a pedir uma coluna inexistente naquele
ponto da cadeia, e **uma instalação nova deixou de conseguir subir do zero** —
sem que nenhum teste percebesse, porque as bases de teste são criadas por
`db.create_all()`, que ignora as migrações.
"""
import os
import pathlib
import re
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
VERSOES = RAIZ / "migrations" / "versions"


def test_instalacao_nova_sobe_do_zero():
    """Percorre a cadeia inteira, do banco vazio ao head. É o caminho de quem
    instala o sistema pela primeira vez, e nenhum outro teste o exercita."""
    from flask_migrate import upgrade

    from config import TestingConfig

    fd, caminho = tempfile.mkstemp(suffix=".sqlite", prefix="ariadne-cadeia-")
    os.close(fd)
    uri_original = TestingConfig.SQLALCHEMY_DATABASE_URI
    TestingConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{caminho}"
    try:
        from app import create_app

        app = create_app("testing")
        with app.app_context():
            upgrade()  # até o head
    finally:
        TestingConfig.SQLALCHEMY_DATABASE_URI = uri_original
        try:
            os.unlink(caminho)
        except OSError:
            pass


@pytest.mark.parametrize(
    "arquivo", sorted(VERSOES.glob("*.py")), ids=lambda p: p.stem[:14]
)
def test_migracao_nao_depende_do_codigo_da_aplicacao(arquivo):
    """Migração precisa continuar replicável para sempre, e o código vivo muda.
    Importar `app.*` amarra a revisão ao estado atual dos modelos — foi assim
    que a cadeia quebrou."""
    fonte = arquivo.read_text(encoding="utf-8")
    # ignora o que estiver dentro de docstring/comentário: interessa o import
    imports = re.findall(r"^\s*(?:from|import)\s+(app[\w.]*)", fonte, re.MULTILINE)
    assert not imports, (
        f"{arquivo.name} importa {imports} — migração não pode depender dos "
        "modelos ou serviços da aplicação"
    )
