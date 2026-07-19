from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.orientandos import bp
from app.blueprints.orientandos.forms import ExcluirForm, OrientandoForm
from app.extensions import db
from app.models import Orientacao, Usuario
from app.services.rbac import role_required
from app.services.usuarios import (
    GestaoUsuarioInvalida,
    criar_usuario,
    excluir_usuario,
    motivo_bloqueio_exclusao,
)


def _meus_orientandos():
    """Orientandos vinculados ao orientador corrente ou criados por ele."""
    vinculados = (
        Usuario.query.join(Orientacao, Orientacao.orientando_id == Usuario.id)
        .filter(Orientacao.orientador_id == current_user.id)
    )
    criados = Usuario.query.filter_by(papel="orientando", criado_por=current_user.id)
    return vinculados.union(criados).order_by(Usuario.nome).all()


@bp.route("/")
@role_required("orientador")
def listar():
    orientandos = _meus_orientandos()
    excluiveis = {
        u.id
        for u in orientandos
        if u.criado_por == current_user.id and motivo_bloqueio_exclusao(u) is None
    }
    return render_template(
        "orientandos/listar.html",
        orientandos=orientandos,
        excluiveis=excluiveis,
        excluir_form=ExcluirForm(),
    )


@bp.route("/novo", methods=["GET", "POST"])
@role_required("orientador")
def criar():
    form = OrientandoForm()
    if form.validate_on_submit():
        try:
            criar_usuario(
                nome=form.nome.data,
                email=form.email.data.lower().strip(),
                papel="orientando",
                senha=form.senha.data,
                autor=current_user,
            )
            db.session.commit()
            flash(
                "Orientando criado. Solicite ao administrador a criação do vínculo "
                "de orientação.",
                "success",
            )
            return redirect(url_for("orientandos.listar"))
        except GestaoUsuarioInvalida as exc:
            flash(str(exc), "danger")
    return render_template("orientandos/form.html", form=form)


@bp.route("/<int:usuario_id>/excluir", methods=["POST"])
@role_required("orientador")
def excluir(usuario_id: int):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    # orientador só exclui contas de orientando que ele próprio criou
    if usuario.papel != "orientando" or usuario.criado_por != current_user.id:
        abort(403)
    form = ExcluirForm()
    if form.validate_on_submit():
        try:
            excluir_usuario(usuario, current_user)
            db.session.commit()
            flash("Conta de orientando excluída.", "success")
        except GestaoUsuarioInvalida as exc:
            db.session.commit()  # persiste o log da recusa
            flash(str(exc), "danger")
    return redirect(url_for("orientandos.listar"))
