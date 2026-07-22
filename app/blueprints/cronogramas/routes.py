from datetime import date

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.cronogramas import bp
from app.blueprints.cronogramas.forms import (
    AnexoMarcoForm,
    ConfirmacaoForm,
    MarcoForm,
    SinalizarForm,
)
from app.extensions import db
from app.models import Documento, Marco
from app.services import auditoria
from app.services.rbac import orientacao_autorizada
from app.services.uploads import UploadInvalido, salvar_versao


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
            tipo=form.tipo.data,
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


@bp.route("/<int:marco_id>")
@login_required
def detalhe(orientacao_id: int, marco_id: int):
    """Página da tarefa: reúne descrição, entregas e reuniões ligadas, a nota do
    orientando, e as ações (anexar, sinalizar, confirmar) conforme o papel."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    return render_template(
        "cronogramas/detalhe.html",
        orientacao=orientacao,
        marco=marco,
        anexo_form=AnexoMarcoForm(titulo=marco.titulo),
        sinalizar_form=SinalizarForm(),
        confirmacao_form=ConfirmacaoForm(),
    )


@bp.route("/<int:marco_id>/anexar", methods=["POST"])
@login_required
def anexar(orientacao_id: int, marco_id: int):
    """Anexa um documento à tarefa: cria um documento ligado ao marco e grava a
    versão 1. Disponível a qualquer participante do vínculo, como em documentos."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = AnexoMarcoForm()
    if form.validate_on_submit():
        documento = Documento(
            orientacao_id=orientacao.id,
            marco_id=marco.id,
            titulo=form.titulo.data,
            criado_por=current_user.id,
        )
        db.session.add(documento)
        db.session.flush()
        try:
            versao = salvar_versao(
                documento, form.arquivo.data, current_user, form.comentario.data
            )
        except UploadInvalido as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            auditoria.registrar(
                "criacao_documento", "documento", documento.id,
                {"titulo": documento.titulo, "arquivo": versao.nome_original,
                 "origem": "marco", "marco_id": marco.id},
            )
            db.session.commit()
            flash("Documento anexado à tarefa (versão 1).", "success")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )


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
    form = SinalizarForm()
    if form.validate_on_submit() and marco.status != "concluido":
        marco.conclusao_sinalizada = True
        marco.status = "em_andamento"
        if form.nota.data:
            marco.nota_conclusao = form.nota.data
        auditoria.registrar(
            "sinalizacao_conclusao_marco", "marco", marco.id,
            {"com_nota": bool(form.nota.data)},
        )
        db.session.commit()
        flash("Conclusão sinalizada; aguardando confirmação do orientador.", "info")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )


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
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )
