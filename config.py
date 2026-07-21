import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "odt", "txt", "zip"}
    # Número de proxies reversos confiáveis à frente da aplicação. Zero desativa
    # a leitura de X-Forwarded-For: sem proxy, o cabeçalho é forjável pelo
    # cliente e registrar seu conteúdo como origem falsearia a auditoria.
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "ariadne-dev.db")
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    # o disparo diário de avisos age em toda requisição; deixá-lo ligado faria
    # testes alheios abrirem conexão SMTP conforme os dados que montassem
    AVISOS_DIARIOS = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    # Bancos servidor (PostgreSQL/MySQL) encerram conexões ociosas; sem isto a
    # primeira requisição após o período de inatividade falharia com conexão
    # morta. Inócuo em SQLite.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    # em produção a aplicação fica atrás do proxy do PythonAnywhere, que
    # acrescenta o endereço do cliente a X-Forwarded-For; sem isto a auditoria
    # grava o IP interno do proxy (10.x.x.x) em vez da origem real
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "1"))
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
