from datetime import UTC, datetime
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.blueprints.auth import bp
from app.blueprints.auth.forms import (
    EsqueciSenhaForm,
    LoginForm,
    RedefinirSenhaForm,
    TrocaSenhaForm,
)
from app.extensions import db
from app.models import Usuario
from app.services import auditoria, recuperacao
from app.services import email as email_service
from app.services.avisos import endereco_do_sistema
from app.services.seguranca import excedeu_tentativas

_EXCESSO = (
    "Muitas tentativas a partir deste endereço. Aguarde alguns minutos e "
    "tente novamente."
)

# Hash descartável, gerado com o mesmo método das senhas reais, para gastar —
# quando o e-mail não existe — o mesmo tempo de uma verificação de verdade. Sem
# isto, a resposta ao e-mail inexistente volta na hora (o hash nunca roda) e o
# tempo distingue conta cadastrada de inexistente, o oráculo que esqueci_senha
# tem o cuidado de não abrir.
_HASH_FALSO = generate_password_hash("conta-inexistente-para-nivelar-o-tempo")


def _destino_seguro(destino: str) -> bool:
    """True se `destino` (o parâmetro `next`) aponta para dentro do próprio site.

    Aceita caminho relativo (`/reunioes`) ou URL absoluta do próprio host; recusa
    tudo que leve para fora. Os casos que a checagem ingênua `not netloc` deixava
    passar e que aqui são barrados um a um: host externo (`//evil.com`,
    `https://evil.com`); a forma opaca (`https:evil.com`, `http:/evil.com`), que
    tem netloc vazio no urlparse mas o navegador lê como host externo; esquema
    perigoso (`javascript:`); e a barra invertida (`/\\evil.com`), que o
    navegador normaliza para `//evil.com` antes de nós."""
    if not destino or "\\" in destino or "\x00" in destino:
        return False
    partes = urlparse(destino)
    if partes.scheme and partes.scheme not in ("http", "https"):
        return False
    if partes.scheme and not partes.netloc:  # opaco: navegador o lê como host
        return False
    if partes.netloc and partes.netloc != urlparse(request.host_url).netloc:
        return False
    return True


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        if excedeu_tentativas():
            auditoria.registrar("login_bloqueado", "usuario",
                                dados={"email": form.email.data})
            db.session.commit()
            flash(_EXCESSO, "danger")
            return render_template("auth/login.html", form=form), 429
        usuario = Usuario.query.filter_by(email=form.email.data.lower().strip()).first()
        # roda um hash mesmo quando o e-mail não existe, para que o tempo de
        # resposta não denuncie quais e-mails têm conta (ver _HASH_FALSO)
        senha_confere = (
            usuario.verificar_senha(form.senha.data)
            if usuario is not None
            else check_password_hash(_HASH_FALSO, form.senha.data)
        )
        if usuario is None or not senha_confere:
            auditoria.registrar("login_falho", "usuario", dados={"email": form.email.data})
            db.session.commit()
            flash("Credenciais inválidas.", "danger")
            return render_template("auth/login.html", form=form), 401
        if not usuario.ativo:
            flash("Conta desativada. Contate o administrador.", "danger")
            return render_template("auth/login.html", form=form), 403
        login_user(usuario, remember=form.lembrar.data)
        # sem isto, PERMANENT_SESSION_LIFETIME é ignorado e a sessão dura o
        # padrão do navegador
        session.permanent = True
        usuario.ultimo_acesso = datetime.now(UTC)
        auditoria.registrar("login", "usuario", usuario.id)
        db.session.commit()
        if usuario.senha_provisoria:
            # o desvio já viria do `before_request`; anunciá-lo aqui evita que
            # a pessoa chegue à tela de troca sem saber por que foi parar nela
            flash(
                "Você entrou com uma senha temporária. Escolha a sua senha "
                "para continuar.",
                "warning",
            )
            return redirect(url_for("auth.trocar_senha"))
        destino = request.args.get("next", "")
        if _destino_seguro(destino):
            return redirect(destino)
        return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    auditoria.registrar("logout", "usuario", current_user.id)
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))


_RESPOSTA_ESQUECI = (
    "Se houver uma conta ativa com esse e-mail, enviamos um link de "
    "recuperação. Confira a caixa de entrada e o spam."
)


@bp.route("/esqueci", methods=["GET", "POST"])
def esqueci_senha():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = EsqueciSenhaForm()
    if form.validate_on_submit():
        if excedeu_tentativas():
            flash(_EXCESSO, "danger")
            return render_template("auth/esqueci.html", form=form), 429

        email = form.email.data.lower().strip()
        usuario = Usuario.query.filter_by(email=email).first()
        # a resposta é a mesma exista ou não a conta: a tela não pode virar
        # oráculo de quem tem cadastro
        if usuario and usuario.ativo:
            _enviar_link(usuario)
            auditoria.registrar("recuperacao_solicitada", "usuario", usuario.id)
        else:
            # registra o pedido infrutífero sem revelar nada ao visitante, e
            # alimenta o limite de tentativas contra sondagem de e-mails
            auditoria.registrar("recuperacao_falha", "usuario", dados={"email": email})
        db.session.commit()
        flash(_RESPOSTA_ESQUECI, "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/esqueci.html", form=form)


def _enviar_link(usuario: Usuario) -> None:
    token = recuperacao.gerar_token(usuario)
    url = endereco_do_sistema()
    link = f"{url}{url_for('auth.redefinir_senha', token=token)}" if url else \
        url_for("auth.redefinir_senha", token=token, _external=True)
    corpo = (
        f"Olá, {usuario.nome}.\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no ARIADNE. "
        "Para escolher uma nova senha, acesse o endereço abaixo, válido por uma "
        "hora:\n\n"
        f"{link}\n\n"
        "Se não foi você que pediu, ignore esta mensagem: a senha atual "
        "permanece válida.\n\n"
        "Mensagem automática; não responda a este e-mail."
    )
    email_service.enviar(usuario.email, "ARIADNE: redefinição de senha", corpo)


@bp.route("/redefinir/<token>", methods=["GET", "POST"])
def redefinir_senha(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    usuario = recuperacao.usuario_do_token(token)
    if usuario is None:
        flash(
            "Link inválido ou expirado. Peça um novo pela opção "
            "\"Esqueci minha senha\".",
            "danger",
        )
        return redirect(url_for("auth.esqueci_senha"))

    form = RedefinirSenhaForm()
    if form.validate_on_submit():
        usuario.set_senha(form.nova_senha.data)
        # a troca muda o hash: tokens pendentes e sessões abertas deixam de valer
        auditoria.registrar("recuperacao_concluida", "usuario", usuario.id)
        db.session.commit()
        flash("Senha redefinida. Entre com a nova senha.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/redefinir.html", form=form)


@bp.route("/senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    """Troca de senha pelo titular. Quando a senha em uso foi gerada pelo
    sistema, esta é a única tela alcançável até que a troca se conclua."""
    obrigatoria = current_user.senha_provisoria
    form = TrocaSenhaForm()
    if form.validate_on_submit():
        if not current_user.verificar_senha(form.senha_atual.data):
            flash("Senha atual incorreta.", "danger")
        elif form.nova_senha.data == form.senha_atual.data:
            # sem isto, a troca obrigatória se cumpriria repetindo a provisória,
            # e a senha que trafegou por e-mail seguiria valendo
            flash("A nova senha deve ser diferente da atual.", "danger")
        else:
            # set_senha limpa a marca de provisória: a senha passa a ser a que
            # só o titular conhece
            current_user.set_senha(form.nova_senha.data)
            # Reemite a identidade da sessão. `get_id` carrega um trecho do
            # hash, de propósito, para que trocar a senha encerre as sessões
            # abertas; sem esta linha isso alcançaria também a sessão de quem
            # acabou de trocar, que era devolvido ao login logo depois de
            # escolher a senha. No primeiro acesso, esse era o primeiro contato
            # de todo usuário novo com o sistema.
            login_user(current_user._get_current_object())
            auditoria.registrar(
                "troca_senha", "usuario", current_user.id,
                {"obrigatoria": obrigatoria} if obrigatoria else None,
            )
            db.session.commit()
            flash("Senha alterada.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template(
        "auth/trocar_senha.html", form=form, obrigatoria=obrigatoria
    )
