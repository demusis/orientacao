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

from app.blueprints.documentos import bp
from app.blueprints.documentos.forms import (
    ClassificarVersaoForm,
    NovaVersaoForm,
    NovoDocumentoForm,
    flags_da_natureza,
)
from app.extensions import db
from app.models import Documento, ModeloDocumento, VersaoDocumento
from app.services import auditoria
from app.services import cronogramas as servico_cronograma
from app.services.rbac import orientacao_autorizada
from app.services.uploads import UploadInvalido, salvar_versao


def _documento_da_orientacao(orientacao, documento_id: int) -> Documento:
    documento = db.session.get(Documento, documento_id)
    if documento is None or documento.orientacao_id != orientacao.id:
        abort(404)
    return documento


@bp.route("/")
@login_required
def listar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    documentos = orientacao.documentos.order_by(Documento.criado_em.desc()).all()
    return render_template(
        "documentos/listar.html", orientacao=orientacao, documentos=documentos
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def criar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    form = NovoDocumentoForm()
    # a versão da orientanda é sempre entrega dela: o campo some para ela (e não
    # é lido no POST)
    eh_gestor = current_user.id != orientacao.orientando_id
    if not eh_gestor:
        del form.natureza
    form.marco_id.choices = [(0, "(nenhum)")] + [
        (m.id, m.titulo) for m in orientacao.marcos
    ]
    if form.validate_on_submit():
        eh_devolucao, em_nome = (
            flags_da_natureza(form.natureza.data) if eh_gestor else (False, False)
        )
        documento = Documento(
            orientacao_id=orientacao.id,
            marco_id=form.marco_id.data or None,
            titulo=form.titulo.data,
            criado_por=current_user.id,
        )
        db.session.add(documento)
        db.session.flush()
        try:
            versao = salvar_versao(
                documento, form.arquivo.data, current_user, form.comentario.data,
                eh_devolucao=eh_devolucao, em_nome_do_orientando=em_nome,
            )
        except UploadInvalido as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            auditoria.registrar(
                "criacao_documento",
                "documento",
                documento.id,
                {"titulo": documento.titulo, "arquivo": versao.nome_original,
                 "natureza": versao.natureza},
            )
            devolvido = (
                eh_devolucao and documento.marco is not None
                and servico_cronograma.devolver_para_revisao(
                    documento.marco, "(devolvido com nova versão)"
                )
            )
            db.session.commit()
            flash("Documento enviado (versão 1).", "success")
            if devolvido:
                flash("Marcada como devolução: a tarefa voltou para revisão do "
                      "orientando.", "info")
            return redirect(url_for("documentos.listar", orientacao_id=orientacao.id))
    modelos = ModeloDocumento.query.order_by(ModeloDocumento.titulo).all()
    return render_template(
        "documentos/form.html", form=form, orientacao=orientacao, modelos=modelos
    )


@bp.route("/<int:documento_id>", methods=["GET", "POST"])
@login_required
def detalhe(orientacao_id: int, documento_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    documento = _documento_da_orientacao(orientacao, documento_id)
    form = NovaVersaoForm()
    eh_gestor = current_user.id != orientacao.orientando_id
    if not eh_gestor:
        del form.natureza
    if form.validate_on_submit():
        # a natureza é declarada pelo gestor; a orientanda sempre entrega
        eh_devolucao, em_nome = (
            flags_da_natureza(form.natureza.data) if eh_gestor else (False, False)
        )
        try:
            versao = salvar_versao(
                documento, form.arquivo.data, current_user, form.comentario.data,
                eh_devolucao=eh_devolucao, em_nome_do_orientando=em_nome,
            )
        except UploadInvalido as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            db.session.flush()  # o id da versão é o que correlaciona log e registro
            auditoria.registrar(
                "nova_versao_documento",
                "versao_documento",
                versao.id,
                {"documento_id": documento.id, "versao": versao.numero_versao,
                 "natureza": versao.natureza},
            )
            # devolução declarada devolve a tarefa ao orientando (se houver marco)
            marco = documento.marco
            devolvido = (
                eh_devolucao and marco is not None
                and servico_cronograma.devolver_para_revisao(
                    marco, "(devolvido com nova versão)"
                )
            )
            db.session.commit()
            flash(f"Versão {versao.numero_versao} enviada.", "success")
            if devolvido:
                flash(
                    "Marcada como devolução: a tarefa voltou para revisão do "
                    "orientando.",
                    "info",
                )
            return redirect(
                url_for(
                    "documentos.detalhe",
                    orientacao_id=orientacao.id,
                    documento_id=documento.id,
                )
            )
    return render_template(
        "documentos/detalhe.html", orientacao=orientacao, documento=documento,
        form=form, eh_gestor=eh_gestor, classificar_form=ClassificarVersaoForm(),
    )


@bp.route("/<int:documento_id>/versoes/<int:versao_id>/classificar", methods=["POST"])
@login_required
def classificar_versao(orientacao_id: int, documento_id: int, versao_id: int):
    """Reclassifica uma versão já enviada (devolução, entrega da orientanda ou
    registro). É a escotilha para acertar envios antigos — e o que decide se a
    versão pede parecer. RBAC do orientador principal/admin."""
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    documento = _documento_da_orientacao(orientacao, documento_id)
    versao = db.session.get(VersaoDocumento, versao_id)
    if versao is None or versao.documento_id != documento.id:
        abort(404)
    form = ClassificarVersaoForm()
    if form.validate_on_submit():
        versao.eh_devolucao, versao.em_nome_do_orientando = flags_da_natureza(
            form.natureza.data
        )
        auditoria.registrar(
            "classificacao_versao", "versao_documento", versao.id,
            {"natureza": versao.natureza},
        )
        db.session.commit()
        flash(
            {
                "devolucao": "Versão marcada como devolução (fora da lista de pareceres).",
                "entrega": "Versão marcada como entrega da orientanda (entra para parecer).",
                "registro": "Versão marcada como registro (não pede parecer).",
            }[versao.natureza],
            "success",
        )
    return redirect(
        url_for("documentos.detalhe", orientacao_id=orientacao.id, documento_id=documento.id)
    )


@bp.route("/<int:documento_id>/versoes/<int:versao_id>/download")
@login_required
def download(orientacao_id: int, documento_id: int, versao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    documento = _documento_da_orientacao(orientacao, documento_id)
    versao = db.session.get(VersaoDocumento, versao_id)
    if versao is None or versao.documento_id != documento.id:
        abort(404)
    auditoria.registrar(
        "download_versao", "versao_documento", versao.id, {"documento_id": documento.id}
    )
    db.session.commit()
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        versao.nome_fisico,
        as_attachment=True,
        download_name=versao.nome_original,
        mimetype=versao.mimetype,
    )
