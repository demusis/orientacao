import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Autentique-se para acessar esta página."
login_manager.login_message_category = "warning"


# SQLite tem um só escritor. Sem estes PRAGMAs, um `commit` que topasse a trava
# de outro escritor (o disparo diário de avisos em before_request, uma tarefa
# agendada, ou dois envios quase simultâneos) falhava com "database is locked",
# virando "Erro interno" na tela — o envio de presenças/deliberações rejeitado
# que, repetido, funcionava. Registrado uma vez, no Engine, para toda conexão:
#
#   busy_timeout — o escritor bloqueado ESPERA (15 s) em vez de falhar na hora;
#   journal_mode=WAL — leitor e escritor deixam de se bloquear.
#
# O backup é exportação lógica das tabelas (não cópia do .db), então os arquivos
# -wal/-shm do WAL não o afetam. Em :memory: (testes) o WAL é ignorado pelo
# próprio SQLite e o busy_timeout é inócuo.
@event.listens_for(Engine, "connect")
def _pragmas_sqlite(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
