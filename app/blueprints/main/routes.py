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


@bp.route("/ajuda")
@login_required
def ajuda():
    return render_template("main/ajuda.html")


@bp.route("/verificar/<tipo>/<int:reg_id>/<hash_informado>")
def verificar(tipo: str, reg_id: int, hash_informado: str):
    """Verificação pública de integridade de documento exportado. Divulga
    apenas a correspondência do hash e o status do registro — nenhum conteúdo."""
    from app.extensions import db
    from app.models import Ata, Parecer
    from app.services import exportacao

    confere = False
    situacao = None
    momento = None
    if tipo == "ata":
        ata = db.session.get(Ata, reg_id)
        if ata is not None and ata.imutavel:
            confere = exportacao.hash_ata(ata) == hash_informado
            situacao = "finalizada"
            momento = ata.finalizada_em
    elif tipo == "parecer":
        parecer = db.session.get(Parecer, reg_id)
        if parecer is not None:
            confere = exportacao.hash_parecer(parecer) == hash_informado
            situacao = "emitido"
            momento = parecer.emitido_em
    else:
        from flask import abort

        abort(404)
    return render_template(
        "main/verificar.html",
        tipo=tipo,
        reg_id=reg_id,
        confere=confere,
        situacao=situacao,
        momento=momento,
    )
