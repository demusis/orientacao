from datetime import date

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.cronogramas import bp
from app.blueprints.cronogramas.forms import ConfirmacaoForm, MarcoForm
from app.extensions import db
from app.models import Marco
from app.models.cronograma import tipo_do_marco
from app.services import auditoria
from app.services.rbac import orientacao_autorizada


def _marco_da_orientacao(orientacao, marco_id: int) -> Marco:
    marco = db.session.get(Marco, marco_id)
    if marco is None or marco.orientacao_id != orientacao.id:
        abort(404)
    return marco


@bp.route("/")
@login_required
def listar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    marcos = orientacao.marcos.all()
    return render_template(
        "cronogramas/listar.html",
        orientacao=orientacao,
        marcos=marcos,
        confirmacao_form=ConfirmacaoForm(),
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def criar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    form = MarcoForm()
    if form.validate_on_submit():
        marco = Marco(
            orientacao_id=orientacao.id,
            titulo=form.titulo.data,
            tipo=tipo_do_marco(form.tipo.data, form.etapa.data),
            descricao=form.descricao.data,
            data_prevista=form.data_prevista.data,
            etapa=form.etapa.data,
        )
        db.session.add(marco)
        db.session.flush()
        auditoria.registrar("criacao_marco", "marco", marco.id, {"titulo": marco.titulo})
        db.session.commit()
        flash("Marco criado.", "success")
        return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
    return render_template("cronogramas/form.html", form=form, orientacao=orientacao)


@bp.route("/<int:marco_id>/editar", methods=["GET", "POST"])
@login_required
def editar(orientacao_id: int, marco_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = MarcoForm(obj=marco)
    if form.validate_on_submit():
        form.populate_obj(marco)
        marco.tipo = tipo_do_marco(form.tipo.data, form.etapa.data)
        auditoria.registrar("edicao_marco", "marco", marco.id)
        db.session.commit()
        flash("Marco atualizado.", "success")
        return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
    return render_template("cronogramas/form.html", form=form, orientacao=orientacao)


@bp.route("/<int:marco_id>/sinalizar", methods=["POST"])
@login_required
def sinalizar_conclusao(orientacao_id: int, marco_id: int):
    """Orientando sinaliza conclusão; efetivação depende do orientador."""
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientando_id:
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = ConfirmacaoForm()
    if form.validate_on_submit() and marco.status != "concluido":
        marco.conclusao_sinalizada = True
        marco.status = "em_andamento"
        auditoria.registrar("sinalizacao_conclusao_marco", "marco", marco.id)
        db.session.commit()
        flash("Conclusão sinalizada; aguardando confirmação do orientador.", "info")
    return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))


@bp.route("/<int:marco_id>/confirmar", methods=["POST"])
@login_required
def confirmar_conclusao(orientacao_id: int, marco_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = ConfirmacaoForm()
    if form.validate_on_submit() and marco.status != "concluido":
        marco.status = "concluido"
        marco.data_conclusao = date.today()
        auditoria.registrar("conclusao_marco", "marco", marco.id)
        db.session.commit()
        flash("Marco concluído.", "success")
    return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
