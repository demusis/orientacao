import os

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app.blueprints.materiais import bp
from app.blueprints.materiais.forms import ExcluirMaterialForm, MaterialForm
from app.extensions import db
from app.models import Material, Orientacao
from app.services import materiais as servico
from app.services.rbac import role_required
from app.services.uploads import (
    UploadInvalido,
    avisar_arquivos_presos,
    remover_do_disco,
)


def _vinculos_ativos():
    return (
        Orientacao.query.filter_by(orientador_id=current_user.id, status="ativa")
        .order_by(Orientacao.titulo_projeto)
        .all()
    )


@bp.route("/", methods=["GET", "POST"])
@role_required("orientador")
def index():
    """Materiais do orientador: publicar um novo e ver/excluir os publicados."""
    vinculos = _vinculos_ativos()
    form = MaterialForm()
    form.orientacoes.choices = [
        (o.id, f"{o.orientando.nome} ({o.titulo_projeto})") for o in vinculos
    ]
    form.tarefa.choices = [("", "(nenhuma)")] + servico.opcoes_de_tarefa(vinculos)
    if form.validate_on_submit():
        escolhidos = [o for o in vinculos if o.id in (form.orientacoes.data or [])]
        marcos = servico.marcos_da_opcao(form.tarefa.data, vinculos)
        try:
            material = servico.publicar(
                titulo=form.titulo.data, descricao=form.descricao.data,
                storage=form.arquivo.data, vinculos=escolhidos, marcos=marcos,
                autor=current_user,
            )
        except UploadInvalido as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            db.session.commit()
            nomes = ", ".join(o.orientando.nome for o in material.orientacoes)
            flash(f'Material "{material.titulo}" disponível para: {nomes}.', "success")
            return redirect(url_for("materiais.index"))
    else:
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
    publicados = (
        Material.query.filter_by(enviado_por=current_user.id)
        .order_by(Material.enviado_em.desc())
        .all()
    )
    return render_template(
        "materiais/index.html", form=form, publicados=publicados,
        excluir_form=ExcluirMaterialForm(), vinculos=vinculos,
    )


@bp.route("/<int:material_id>/download")
@login_required
def download(material_id: int):
    """Só quem o material alcança: autor, admin e participantes dos vínculos
    com que foi compartilhado. Os demais recebem 404 — revelar que o material
    existe já seria informação."""
    material = db.session.get(Material, material_id)
    if material is None or not servico.pode_ver(material, current_user):
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        material.nome_fisico,
        as_attachment=True,
        download_name=material.nome_original,
        mimetype=material.mimetype,
    )


@bp.route("/<int:material_id>/excluir", methods=["POST"])
@login_required
def excluir(material_id: int):
    material = db.session.get(Material, material_id)
    if material is None or not servico.pode_ver(material, current_user):
        abort(404)
    if not servico.pode_excluir(material, current_user):
        abort(403)
    form = ExcluirMaterialForm()
    if form.validate_on_submit():
        titulo = material.titulo
        nome = servico.excluir(material)
        db.session.commit()
        pasta = current_app.config["UPLOAD_FOLDER"]
        avisar_arquivos_presos(remover_do_disco([os.path.join(pasta, nome)]), "a exclusão")
        flash(f'Material "{titulo}" excluído; deixou de estar disponível.', "success")
    return redirect(url_for("materiais.index"))
