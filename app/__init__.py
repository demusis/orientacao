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

    # atrás de proxy reverso, request.remote_addr é o endereço do próprio proxy;
    # x_for=N faz o Werkzeug tomar o N-ésimo valor a partir da direita em
    # X-Forwarded-For — o mais à direita é o que o proxy confiável escreveu,
    # portanto não é falseável por cabeçalho enviado pelo cliente
    proxies = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if proxies:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies
        )

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
    from app.blueprints.orientandos import bp as orientandos_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(main_bp)
    app.register_blueprint(cronogramas_bp, url_prefix="/orientacoes/<int:orientacao_id>/cronograma")
    app.register_blueprint(documentos_bp, url_prefix="/orientacoes/<int:orientacao_id>/documentos")
    app.register_blueprint(atas_bp, url_prefix="/orientacoes/<int:orientacao_id>")
    app.register_blueprint(reunioes_bp, url_prefix="/reunioes")
    app.register_blueprint(orientandos_bp, url_prefix="/orientandos")

    register_cli(app)
    register_template_globals(app)
    register_avisos_diarios(app)
    return app


def register_avisos_diarios(app: Flask) -> None:
    """Dispara os avisos de pendência uma vez por dia, aproveitando o tráfego.

    O plano gratuito da hospedagem não oferece agendador (ver `services/avisos.py`).
    Na prática o site recebe centenas de requisições por mês, então o envio sai
    no primeiro acesso de cada dia; um dia inteiro sem visitas adia para o
    seguinte.

    Três cuidados: o banco é consultado no máximo uma vez por intervalo de
    repetição, graças ao marcador em memória; a trava de concorrência é o UPDATE
    condicional de `avisos.reservar_tentativa`; e falha alguma pode derrubar a
    requisição do usuário, que nada tem a ver com o envio."""
    from datetime import datetime, timezone

    # até quando não vale a pena nem consultar o banco
    estado = {"proxima_verificacao": None}

    @app.before_request
    def disparar_avisos_do_dia():
        from flask import request

        # Desligado na suíte por padrão: um gatilho que dispara sozinho em toda
        # requisição faria testes alheios abrirem conexão SMTP conforme os dados
        # que montassem. Os testes do próprio gatilho o habilitam explicitamente.
        if not app.config.get("AVISOS_DIARIOS", True):
            return
        # arquivo estático não deve pagar nem a comparação de data
        if request.endpoint == "static":
            return
        agora = datetime.now(timezone.utc).replace(tzinfo=None)
        if estado["proxima_verificacao"] and agora < estado["proxima_verificacao"]:
            return

        from app.extensions import db
        from app.models import ConfiguracaoEmail
        from app.services import auditoria, avisos

        estado["proxima_verificacao"] = agora + avisos.INTERVALO_ENTRE_TENTATIVAS
        try:
            if not ConfiguracaoEmail.vigente().operante:
                db.session.commit()
                return
            resumo = avisos.disparar_se_devido()
            if resumo is not None:
                auditoria.registrar(
                    "envio_avisos", "configuracao_email", 1, resumo
                )
            db.session.commit()
        except Exception:  # noqa: BLE001 — nada aqui pode quebrar a requisição
            db.session.rollback()
            app.logger.exception("Falha ao disparar os avisos do dia")


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

    @app.cli.command("indicadores")
    @click.option("--dias", default=30, help="Janela de análise da trilha, em dias.")
    @click.option("--json", "como_json", is_flag=True, help="Saída em JSON.")
    def indicadores(dias: int, como_json: bool):
        """Indicadores agregados de uso, para o ciclo de avaliação."""
        import json as _json

        from app.services.indicadores import coletar

        dados = coletar(dias)
        if como_json:
            click.echo(_json.dumps(dados, ensure_ascii=False, indent=2, default=str))
            return
        for secao, conteudo in dados.items():
            if not isinstance(conteudo, dict):
                click.echo(f"{secao}: {conteudo}")
                continue
            click.echo(f"\n[{secao}]")
            for chave, valor in conteudo.items():
                click.echo(f"  {chave}: {valor}")


def register_template_globals(app: Flask) -> None:
    from app.models.orientacao import MODALIDADE_LABEL, TIPO_EVENTO_LABEL
    from app.models.ata import RESULTADO_LABEL
    from app.models.cronograma import ETAPA_MARCO_LABEL, TIPO_MARCO_LABEL

    app.jinja_env.globals.update(
        ETAPA_MARCO_LABEL=ETAPA_MARCO_LABEL,
        MODALIDADE_LABEL=MODALIDADE_LABEL,
        RESULTADO_LABEL=RESULTADO_LABEL,
        TIPO_EVENTO_LABEL=TIPO_EVENTO_LABEL,
        TIPO_MARCO_LABEL=TIPO_MARCO_LABEL,
    )

    # mesmo emissor que alimenta o PDF, para que a tela não divirja do assinado
    from app.services.marcacao import para_html

    app.jinja_env.filters["marcacao"] = para_html
