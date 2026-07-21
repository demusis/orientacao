from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from urllib.parse import urlparse

from app.blueprints.auth import bp
from app.blueprints.auth.forms import LoginForm, TrocaSenhaForm
from app.extensions import db
from app.models import Usuario
from app.services import auditoria
from app.services.seguranca import excedeu_tentativas

_EXCESSO = (
    "Muitas tentativas a partir deste endereço. Aguarde alguns minutos e "
    "tente novamente."
)


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
        if usuario is None or not usuario.verificar_senha(form.senha.data):
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
        usuario.ultimo_acesso = datetime.now(timezone.utc)
        auditoria.registrar("login", "usuario", usuario.id)
        db.session.commit()
        destino = request.args.get("next", "")
        if destino and not urlparse(destino).netloc:
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


@bp.route("/senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    form = TrocaSenhaForm()
    if form.validate_on_submit():
        if not current_user.verificar_senha(form.senha_atual.data):
            flash("Senha atual incorreta.", "danger")
        else:
            current_user.set_senha(form.nova_senha.data)
            auditoria.registrar("troca_senha", "usuario", current_user.id)
            db.session.commit()
            flash("Senha alterada.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/trocar_senha.html", form=form)
