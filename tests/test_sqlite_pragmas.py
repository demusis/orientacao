"""PRAGMAs de conexão do SQLite (extensions._pragmas_sqlite): busy_timeout e
WAL, o reforço contra "database is locked" transitório no salvamento de atas."""
from sqlalchemy import create_engine, text

from app.extensions import db


def test_busy_timeout_configurado(app):
    # o escritor bloqueado espera 15 s em vez de falhar na hora
    with app.app_context():
        valor = db.session.execute(text("PRAGMA busy_timeout")).scalar()
    assert valor == 15000


def test_wal_em_banco_de_arquivo(tmp_path):
    # :memory: ignora WAL; um banco de arquivo exercita o listener de verdade
    engine = create_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    try:
        with engine.connect() as conn:
            modo = conn.execute(text("PRAGMA journal_mode")).scalar()
            espera = conn.execute(text("PRAGMA busy_timeout")).scalar()
    finally:
        engine.dispose()
    assert modo == "wal"
    assert espera == 15000
