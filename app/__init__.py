import os
from datetime import UTC

import click
from flask import Flask

from app.extensions import csrf, db, login_manager, migrate
from config import config_by_name


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
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.atas import bp as atas_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.cronogramas import bp as cronogramas_bp
    from app.blueprints.documentos import bp as documentos_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.orientandos import bp as orientandos_bp
    from app.blueprints.reunioes import bp as reunioes_bp

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
    register_seguranca(app)
    register_erros(app)
    return app


def register_seguranca(app: Flask) -> None:
    """Cabeçalhos de segurança em toda resposta.

    A política de conteúdo é estrita porque pode ser: os templates da aplicação
    não têm um único `style=` embutido nem uma tag `<script>` — o projeto não
    usa JavaScript. Assim proíbe-se `script-src` por inteiro e dispensa-se o
    `'unsafe-inline'` que a maioria dos sites é obrigada a abrir. Um recurso que
    a política venha a barrar aparece no console do navegador, e é ali que se
    confere após qualquer mudança de template."""
    csp = (
        "default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "  # dispensa X-Frame-Options
        "base-uri 'none'"
    )

    @app.after_request
    def aplicar_cabecalhos(resposta):
        resposta.headers.setdefault("Content-Security-Policy", csp)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        # HSTS só faz sentido — e só é honrado — sob HTTPS
        if app.config.get("SESSION_COOKIE_SECURE"):
            resposta.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resposta


def register_erros(app: Flask) -> None:
    """Páginas de erro na identidade do sistema. O 500 registra a exceção no log
    e jamais a expõe ao usuário; os demais explicam o que houve e o que fazer."""
    from flask import render_template

    def pagina(codigo: int, titulo: str, mensagem: str):
        def handler(erro):
            return render_template(
                "erros/erro.html", codigo=codigo, titulo=titulo, mensagem=mensagem
            ), codigo
        return handler

    app.register_error_handler(
        403,
        pagina(403, "Acesso negado",
               "Você não tem permissão para acessar esta página."),
    )
    app.register_error_handler(
        404,
        pagina(404, "Página não encontrada",
               "O endereço não existe ou o registro foi removido."),
    )
    app.register_error_handler(
        413,
        pagina(413, "Arquivo grande demais",
               "O envio excede o limite de 20 MB. Reduza o arquivo e tente de novo."),
    )

    @app.errorhandler(500)
    def erro_interno(erro):
        app.logger.exception("Erro interno não tratado")
        return render_template(
            "erros/erro.html",
            codigo=500,
            titulo="Erro interno",
            mensagem="Algo falhou de nosso lado. O incidente foi registrado; "
            "tente novamente em instantes.",
        ), 500


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
    from datetime import datetime

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
        agora = datetime.now(UTC).replace(tzinfo=None)
        if estado["proxima_verificacao"] and agora < estado["proxima_verificacao"]:
            return

        from app.extensions import db
        from app.models import ConfiguracaoEmail
        from app.services import auditoria, avisos

        estado["proxima_verificacao"] = agora + avisos.INTERVALO_ENTRE_TENTATIVAS
        resumo = None
        try:
            if not ConfiguracaoEmail.vigente().operante:
                db.session.commit()
                return
            # confirma internamente a reserva antes da rede e o registro de
            # entrega logo após; o que sobra para cá é só a auditoria
            resumo = avisos.disparar_se_devido()
        except Exception:  # noqa: BLE001 — nada aqui pode quebrar a requisição
            db.session.rollback()
            app.logger.exception("Falha ao disparar os avisos do dia")
            return

        if resumo is None:
            return
        try:
            # Transação própria, posterior à que registrou as entregas. Antes,
            # uma falha aqui provocava rollback das marcas de envio e o lote
            # inteiro era reenviado na janela seguinte — perder uma linha da
            # trilha é muito menos grave que duplicar aviso a todos.
            auditoria.registrar(
                "envio_avisos", "configuracao_email", 1, resumo, automatico=True
            )
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            app.logger.exception("Avisos enviados, mas a auditoria falhou: %s", resumo)


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
    from app.models.ata import RESULTADO_LABEL
    from app.models.cronograma import ETAPA_MARCO_LABEL, TIPO_MARCO_LABEL
    from app.models.orientacao import MODALIDADE_LABEL, TIPO_EVENTO_LABEL

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
