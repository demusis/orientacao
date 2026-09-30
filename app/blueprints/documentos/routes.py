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
    eh_entrega_da_orientanda,
)
from app.extensions import db
from app.models import AnexoVersao, Documento, ModeloDocumento, VersaoDocumento
from app.services import auditoria
from app.services.rbac import manda_no_cronograma, orientacao_autorizada
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
    # a versão da orientanda é sempre entrega dela: o campo some para ela. O
    # upload só grava a versão — devolver é ação da tarefa, não do envio.
    eh_gestor = current_user.id != orientacao.orientando_id
    if not eh_gestor:
        del form.natureza
    form.marco_id.choices = [(0, "(nenhum)")] + [
        (m.id, m.titulo) for m in orientacao.marcos
    ]
    if form.validate_on_submit():
        em_nome = eh_gestor and eh_entrega_da_orientanda(form.natureza.data)
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
                documento, form.arquivo.data or None, current_user,
                form.comentario.data, em_nome_do_orientando=em_nome,
                anexos=form.anexos.data,
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
                 "anexos": len(versao.anexos), "natureza": versao.natureza},
            )
            db.session.commit()
            flash("Documento enviado (versão 1).", "success")
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
        # a orientanda sempre entrega; o gestor diz de quem é o arquivo. O upload
        # só grava a versão — devolver é ação da tarefa, não do envio.
        em_nome = eh_gestor and eh_entrega_da_orientanda(form.natureza.data)
        try:
            versao = salvar_versao(
                documento, form.arquivo.data or None, current_user,
                form.comentario.data, em_nome_do_orientando=em_nome,
                anexos=form.anexos.data,
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
                 "anexos": len(versao.anexos), "natureza": versao.natureza},
            )
            db.session.commit()
            flash(f"Versão {versao.numero_versao} enviada.", "success")
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
    """Reclassifica de quem é uma versão já enviada — registro meu ou entrega da
    orientanda. É o eixo de parecer, e a escotilha para acertar envios antigos.
    Devolver é ação da tarefa (à parte); reclassificar aqui também tira a etiqueta
    de devolução, se houver (uma versão que se declara registro/entrega não é
    devolução). RBAC do orientador principal/admin."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    documento = _documento_da_orientacao(orientacao, documento_id)
    versao = db.session.get(VersaoDocumento, versao_id)
    if versao is None or versao.documento_id != documento.id:
        abort(404)
    if versao.enviada_pela_orientanda:
        flash(
            "Esta versão foi enviada pela orientanda: é entrega dela, não há o que "
            "classificar.",
            "info",
        )
        return redirect(
            url_for("documentos.detalhe", orientacao_id=orientacao.id, documento_id=documento.id)
        )
    form = ClassificarVersaoForm()
    if form.validate_on_submit():
        versao.em_nome_do_orientando = eh_entrega_da_orientanda(form.natureza.data)
        versao.eh_devolucao = False
        auditoria.registrar(
            "classificacao_versao", "versao_documento", versao.id,
            {"natureza": versao.natureza},
        )
        db.session.commit()
        flash(
            "Versão marcada como entrega da orientanda (entra para parecer)."
            if versao.em_nome_do_orientando
            else "Versão marcada como registro (não pede parecer).",
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
    if not versao.tem_arquivo:
        abort(404)  # versão só comentário: não há arquivo a baixar
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


@bp.route(
    "/<int:documento_id>/versoes/<int:versao_id>/anexos/<int:anexo_id>/download"
)
@login_required
def download_anexo(orientacao_id: int, documento_id: int, versao_id: int, anexo_id: int):
    """Mesmo controle de acesso do download da versão: o anexo só é alcançável
    pela cadeia orientação → documento → versão, cada elo conferido."""
    orientacao = orientacao_autorizada(orientacao_id)
    documento = _documento_da_orientacao(orientacao, documento_id)
    anexo = db.session.get(AnexoVersao, anexo_id)
    if (
        anexo is None
        or anexo.versao_id != versao_id
        or anexo.versao.documento_id != documento.id
    ):
        abort(404)
    auditoria.registrar(
        "download_versao", "versao_documento", versao_id,
        {"documento_id": documento.id, "anexo_id": anexo.id},
    )
    db.session.commit()
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        anexo.nome_fisico,
        as_attachment=True,
        download_name=anexo.nome_original,
        mimetype=anexo.mimetype,
    )
