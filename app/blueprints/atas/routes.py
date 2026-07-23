from flask import (
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.blueprints.atas import bp
from app.blueprints.atas.forms import (
    AcaoForm,
    AtaEdicaoForm,
    AtaForm,
    FinalizarAtaForm,
    ParecerForm,
    ReagendarForm,
)
from app.extensions import db
from app.models import Ata, AtaParticipacao, Documento, Parecer, VersaoDocumento
from app.services import auditoria, convites, exportacao
from app.services.atas import (
    AtaImutavel,
    OperacaoInvalida,
    atualizar_ata,
    finalizar_ata,
    limpar_link,
    reagendar_ata,
    registrar_presenca,
)
from app.services.rbac import orientacao_autorizada


def _ata_da_orientacao(orientacao, ata_id: int) -> Ata:
    ata = db.session.get(Ata, ata_id)
    if ata is None or orientacao not in ata.orientacoes:
        abort(404)
    return ata


def _autorizacoes(ata: Ata) -> tuple[bool, set[int]]:
    """Exame único dos vínculos participantes. Devolve (pode_editar, geríveis):
    edição do texto cabe ao admin, ao orientador convocante ou a quem integra a
    equipe de TODOS os vínculos; presença é assinalável por vínculo — todos,
    para convocante e admin; apenas os próprios, para coorientadores."""
    todos = {p.orientacao_id for p in ata.participacoes}
    if current_user.papel == "admin" or current_user.id == ata.orientador_id:
        return True, todos
    geriveis = {
        p.orientacao_id
        for p in ata.participacoes
        if p.orientacao.orienta(current_user)
    }
    return bool(todos) and geriveis == todos, geriveis


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
    if not orientacao.orienta(current_user) and current_user.papel != "admin":
        abort(403)
    form = AtaForm()
    marcos = orientacao.marcos.all()
    form.marcos.choices = [(m.id, m.titulo) for m in marcos]
    if form.validate_on_submit():
        ata = Ata(
            tipo="individual",
            orientador_id=orientacao.orientador_id,
            data_reuniao=form.data_reuniao.data,
            hora_reuniao=form.hora_reuniao.data,
            link_reuniao=limpar_link(form.link_reuniao.data),
            pauta=form.pauta.data,
            deliberacoes=form.deliberacoes.data,
            redigida_por=current_user.id,
            participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
            marcos=[m for m in marcos if m.id in form.marcos.data],
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
    pode_editar_base, geriveis = _autorizacoes(ata)
    pode_editar = pode_editar_base and not ata.imutavel

    form = AtaEdicaoForm(obj=ata)
    finalizar_form = FinalizarAtaForm()

    # marcos elegíveis: dos vínculos participantes (ata individual ou de grupo)
    marcos_disponiveis = [
        m for o in ata.orientacoes for m in o.marcos
    ]
    form.marcos.choices = [(m.id, m.titulo) for m in marcos_disponiveis]
    if request.method == "GET":
        form.marcos.data = [m.id for m in ata.marcos]

    if pode_editar and form.submit.data and form.validate_on_submit():
        try:
            atualizar_ata(
                ata,
                pauta=form.pauta.data,
                deliberacoes=form.deliberacoes.data,
                marcos=[m for m in marcos_disponiveis if m.id in form.marcos.data],
                link=form.link_reuniao.data,
            )
            db.session.commit()
            flash("Ata atualizada.", "success")
        except (AtaImutavel, OperacaoInvalida) as exc:
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
        geriveis=geriveis,
        pode_finalizar=current_user.id == ata.orientador_id
        or current_user.papel == "admin",
        acao_form=AcaoForm(),
    )


@bp.route("/atas/<int:ata_id>/reagendar", methods=["GET", "POST"])
@login_required
def reagendar(orientacao_id: int, ata_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    ata = _ata_da_orientacao(orientacao, ata_id)
    if current_user.id != ata.orientador_id and current_user.papel != "admin":
        abort(403)
    form = ReagendarForm(data_reuniao=ata.data_reuniao, hora_reuniao=ata.hora_reuniao)
    if form.validate_on_submit():
        try:
            reagendar_ata(
                ata,
                current_user,
                data_nova=form.data_reuniao.data,
                hora_nova=form.hora_reuniao.data,
                motivo=form.motivo.data,
            )
            db.session.commit()
            flash("Reunião reagendada; o histórico foi registrado.", "success")
            # o aviso vai depois do commit: falar com o SMTP dentro da
            # transação seguraria a trava de escrita do SQLite
            entregues, falhas = convites.notificar(ata, "remarcada")
            db.session.commit()
            flash(*convites.mensagem_de_resultado(entregues, falhas))
        except AtaImutavel as exc:
            db.session.commit()  # persiste o log da tentativa
            flash(str(exc), "danger")
        return redirect(
            url_for("atas.detalhe_ata", orientacao_id=orientacao.id, ata_id=ata.id)
        )
    return render_template(
        "atas/reagendar.html", orientacao=orientacao, ata=ata, form=form
    )


@bp.route(
    "/atas/<int:ata_id>/presenca/<int:alvo_id>/<presenca>", methods=["POST"]
)
@login_required
def marcar_presenca(orientacao_id: int, ata_id: int, alvo_id: int, presenca: str):
    orientacao = orientacao_autorizada(orientacao_id)
    ata = _ata_da_orientacao(orientacao, ata_id)
    participacao = ata.participacao_de(alvo_id)
    if participacao is None:
        abort(404)
    # a autorização é sobre o vínculo-alvo, não sobre a ata como um todo
    if alvo_id not in _autorizacoes(ata)[1]:
        abort(403)
    form = AcaoForm()
    if form.validate_on_submit():
        try:
            registrar_presenca(participacao, presenca, current_user)
            db.session.commit()
            flash("Presença registrada.", "success")
        except (AtaImutavel, OperacaoInvalida) as exc:
            db.session.commit()  # persiste o log da tentativa
            flash(str(exc), "danger")
    return redirect(
        url_for("atas.detalhe_ata", orientacao_id=orientacao.id, ata_id=ata.id)
    )


# Rota de justificativa de ausência retirada em 19/07/2026 (decisão LGPD:
# potencial dado sensível). Reintrodução exigirá base legal definida.


@bp.route("/atas/<int:ata_id>/pdf")
@login_required
def pdf_ata(orientacao_id: int, ata_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    ata = _ata_da_orientacao(orientacao, ata_id)
    # `imutavel` abrange a cancelada, que não tem ata: exportá-la produziria um
    # PDF assinável com deliberações em branco e um hash aparentemente válido
    if ata.status != "finalizada":
        flash("Apenas atas finalizadas podem ser exportadas.", "warning")
        return redirect(
            url_for("atas.detalhe_ata", orientacao_id=orientacao.id, ata_id=ata.id)
        )
    url_verificacao = url_for(
        "main.verificar",
        tipo="ata",
        reg_id=ata.id,
        hash_informado=exportacao.hash_ata(ata),
        _external=True,
    )
    pdf = exportacao.gerar_pdf_ata(ata, url_verificacao)
    auditoria.registrar("exportacao_pdf", "ata", ata.id)
    db.session.commit()
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ariadne-ata-{ata.id}.pdf"},
    )


@bp.route("/pareceres/<int:parecer_id>/pdf")
@login_required
def pdf_parecer(orientacao_id: int, parecer_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    parecer = db.session.get(Parecer, parecer_id)
    if parecer is None or parecer.orientacao_id != orientacao.id:
        abort(404)
    url_verificacao = url_for(
        "main.verificar",
        tipo="parecer",
        reg_id=parecer.id,
        hash_informado=exportacao.hash_parecer(parecer),
        _external=True,
    )
    pdf = exportacao.gerar_pdf_parecer(parecer, url_verificacao)
    auditoria.registrar("exportacao_pdf", "parecer", parecer.id)
    db.session.commit()
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=ariadne-parecer-{parecer.id}.pdf"
        },
    )


@bp.route("/atas/<int:ata_id>/finalizar", methods=["POST"])
@login_required
def finalizar(orientacao_id: int, ata_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    ata = _ata_da_orientacao(orientacao, ata_id)
    if current_user.id != ata.orientador_id and current_user.papel != "admin":
        abort(403)
    form = FinalizarAtaForm()
    if form.validate_on_submit():
        try:
            finalizar_ata(ata)
            db.session.commit()
            flash("Ata finalizada. O registro tornou-se imutável.", "success")
        except (AtaImutavel, OperacaoInvalida) as exc:
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
    form.versao_documento_id.choices = [(0, "(nenhuma)")] + [
        (v.id, f"{v.documento.titulo} (v{v.numero_versao})") for v in versoes
    ]

    # Chegada pelo Painel: a versão vem no endereço já escolhida. O parâmetro é
    # confrontado com as versões DESTA orientação — o acesso já passou por
    # `orientacao_autorizada`, mas identificador de outro vínculo não pode ser
    # pré-selecionado nem revelar na tela o título de documento alheio.
    avaliada = next(
        (v for v in versoes if v.id == request.args.get("versao", type=int)), None
    )
    if request.method == "GET" and avaliada:
        form.versao_documento_id.data = avaliada.id
        # avaliar uma entrega é justamente o caso do tipo "documento", que fixa
        # exatamente o que foi apreciado
        form.tipo.data = "documento"

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
        exportacao.congelar_parecer(parecer)
        auditoria.registrar(
            "emissao_parecer",
            "parecer",
            parecer.id,
            {"tipo": parecer.tipo, "resultado": parecer.resultado},
        )
        db.session.commit()
        flash("Parecer emitido. O registro é imutável.", "success")
        return redirect(url_for("atas.listar_pareceres", orientacao_id=orientacao.id))

    return render_template(
        "atas/parecer_form.html",
        form=form,
        orientacao=orientacao,
        avaliada=avaliada,
        # o Painel é leitura de momento: pode-se chegar por link envelhecido,
        # depois de a versão já ter sido avaliada
        parecer_existente=(
            Parecer.query.filter_by(versao_documento_id=avaliada.id).first()
            if avaliada
            else None
        ),
    )
