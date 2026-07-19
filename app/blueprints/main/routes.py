from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.main import bp
from app.models import Orientacao
from app.services.rbac import orientacao_autorizada, orientacoes_do_usuario


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    orientacoes = orientacoes_do_usuario().order_by(Orientacao.criado_em.desc()).all()
    marcos_atrasados = [
        m for o in orientacoes if o.status == "ativa" for m in o.marcos if m.atrasado
    ]
    return render_template(
        "main/dashboard.html",
        orientacoes=orientacoes,
        marcos_atrasados=marcos_atrasados,
    )


@bp.route("/orientacoes/<int:orientacao_id>")
@login_required
def orientacao_detalhe(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    return render_template("main/orientacao_detalhe.html", orientacao=orientacao)
