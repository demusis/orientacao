import os

import click
from flask import Flask

from config import config_by_name
from app.extensions import csrf, db, login_manager, migrate


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    if config_name == "development":
        os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registro dos mapeamentos)

    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.cronogramas import bp as cronogramas_bp
    from app.blueprints.documentos import bp as documentos_bp
    from app.blueprints.atas import bp as atas_bp
    from app.blueprints.reunioes import bp as reunioes_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(main_bp)
    app.register_blueprint(cronogramas_bp, url_prefix="/orientacoes/<int:orientacao_id>/cronograma")
    app.register_blueprint(documentos_bp, url_prefix="/orientacoes/<int:orientacao_id>/documentos")
    app.register_blueprint(atas_bp, url_prefix="/orientacoes/<int:orientacao_id>")
    app.register_blueprint(reunioes_bp, url_prefix="/reunioes")

    register_cli(app)
    register_template_globals(app)
    return app


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-admin")
    @click.option("--nome", default="Administrador")
    @click.option("--email", required=True)
    @click.option("--senha", required=True)
    def seed_admin(nome: str, email: str, senha: str):
        """Cria o usuário administrador inicial."""
        from email_validator import EmailNotValidError, validate_email

        from app.models import Usuario

        # mesma validação do formulário de login; evita semear e-mail inutilizável
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as exc:
            raise click.ClickException(f"E-mail inválido: {exc}")

        if Usuario.query.filter_by(email=email).first():
            click.echo(f"Usuário {email} já existe.")
            return
        admin = Usuario(nome=nome, email=email, papel="admin")
        admin.set_senha(senha)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Administrador {email} criado.")


def register_template_globals(app: Flask) -> None:
    from app.models.orientacao import MODALIDADE_LABEL
    from app.models.ata import RESULTADO_LABEL

    app.jinja_env.globals.update(
        MODALIDADE_LABEL=MODALIDADE_LABEL,
        RESULTADO_LABEL=RESULTADO_LABEL,
    )
