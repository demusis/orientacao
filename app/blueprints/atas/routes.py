from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.atas import bp
from app.blueprints.atas.forms import AtaForm, FinalizarAtaForm, ParecerForm
from app.extensions import db
from app.models import Ata, Parecer, VersaoDocumento, Documento
from app.services import auditoria
from app.services.atas import AtaImutavel, atualizar_ata, finalizar_ata
from app.services.rbac import orientacao_autorizada


def _ata_da_orientacao(orientacao, ata_id: int) -> Ata:
    ata = db.session.get(Ata, ata_id)
    if ata is None or ata.orientacao_id != orientacao.id:
        abort(404)
    return ata


@bp.route("/atas")
@login_required
def listar_atas(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    atas = orientacao.atas.order_by(Ata.data_reuniao.desc()).all()
    return render_template("atas/listar.html", orientacao=orientacao, atas=atas)


@bp.route("/atas/nova", methods=["GET", "POST"])
@login_required
def criar_ata(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    form = AtaForm()
    if form.validate_on_submit():
        ata = Ata(
            orientacao_id=orientacao.id,
            data_reuniao=form.data_reuniao.data,
            pauta=form.pauta.data,
            deliberacoes=form.deliberacoes.data,
            redigida_por=current_user.id,
        )
        db.session.add(ata)
        db.session.flush()
        auditoria.registrar("criacao_ata", "ata", ata.id)
        db.session.commit()
        flash("Ata registrada como rascunho.", "success")
        return redirect(url_for("atas.listar_atas", orientacao_id=orientacao.id))
    return render_template("atas/form.html", form=form, orientacao=orientacao)


@bp.route("/atas/<int:ata_id>", methods=["GET", "POST"])
@login_required
def detalhe_ata(orientacao_id: int, ata_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    ata = _ata_da_orientacao(orientacao, ata_id)
    pode_editar = (
        current_user.id == orientacao.orientador_id or current_user.papel == "admin"
    ) and not ata.imutavel

    form = AtaForm(obj=ata)
    finalizar_form = FinalizarAtaForm()

    if pode_editar and form.submit.data and form.validate_on_submit():
        try:
            atualizar_ata(
                ata,
                data_reuniao=form.data_reuniao.data,
                pauta=form.pauta.data,
                deliberacoes=form.deliberacoes.data,
            )
            db.session.commit()
            flash("Ata atualizada.", "success")
        except AtaImutavel as exc:
            db.session.commit()  # persiste o log da tentativa
            flash(str(exc), "danger")
        return redirect(
            url_for("atas.detalhe_ata", orientacao_id=orientacao.id, ata_id=ata.id)
        )

    return render_template(
        "atas/detalhe.html",
        orientacao=orientacao,
        ata=ata,
        form=form,
        finalizar_form=finalizar_form,
        pode_editar=pode_editar,
    )


@bp.route("/atas/<int:ata_id>/finalizar", methods=["POST"])
@login_required
def finalizar(orientacao_id: int, ata_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    ata = _ata_da_orientacao(orientacao, ata_id)
    form = FinalizarAtaForm()
    if form.validate_on_submit():
        try:
            finalizar_ata(ata)
            db.session.commit()
            flash("Ata finalizada. O registro tornou-se imutável.", "success")
        except AtaImutavel as exc:
            flash(str(exc), "warning")
    return redirect(
        url_for("atas.detalhe_ata", orientacao_id=orientacao.id, ata_id=ata.id)
    )


@bp.route("/pareceres")
@login_required
def listar_pareceres(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    pareceres = orientacao.pareceres.order_by(Parecer.emitido_em.desc()).all()
    return render_template(
        "atas/pareceres.html", orientacao=orientacao, pareceres=pareceres
    )


@bp.route("/pareceres/novo", methods=["GET", "POST"])
@login_required
def emitir_parecer(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        abort(403)
    form = ParecerForm()
    versoes = (
        db.session.query(VersaoDocumento)
        .join(Documento)
        .filter(Documento.orientacao_id == orientacao.id)
        .order_by(VersaoDocumento.enviado_em.desc())
        .all()
    )
    form.versao_documento_id.choices = [(0, "— nenhuma —")] + [
        (v.id, f"{v.documento.titulo} (v{v.numero_versao})") for v in versoes
    ]
    if form.validate_on_submit():
        parecer = Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=form.versao_documento_id.data or None,
            tipo=form.tipo.data,
            conteudo=form.conteudo.data,
            resultado=form.resultado.data,
            emitido_por=current_user.id,
        )
        db.session.add(parecer)
        db.session.flush()
        auditoria.registrar(
            "emissao_parecer",
            "parecer",
            parecer.id,
            {"tipo": parecer.tipo, "resultado": parecer.resultado},
        )
        db.session.commit()
        flash("Parecer emitido. O registro é imutável.", "success")
        return redirect(url_for("atas.listar_pareceres", orientacao_id=orientacao.id))
    return render_template("atas/parecer_form.html", form=form, orientacao=orientacao)
