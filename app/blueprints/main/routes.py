from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.main import bp
from app.blueprints.main.forms import TituloProjetoForm
from app.extensions import db
from app.models import Orientacao
from app.services import eventos as eventos_service
from app.services import linha_tempo, painel, relatorio
from app.services.eventos import EventoInvalido
from app.services.rbac import orientacao_autorizada, orientacoes_do_usuario


def _pode_alterar_titulo(orientacao) -> bool:
    """Título do projeto: orientador principal do vínculo ou administrador."""
    return (
        current_user.id == orientacao.orientador_id or current_user.papel == "admin"
    )


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    orientacoes = orientacoes_do_usuario().order_by(Orientacao.criado_em.desc()).all()
    return render_template(
        "main/dashboard.html",
        orientacoes=orientacoes,
        pendencias=painel.pendencias(),
    )


@bp.route("/orientacoes/<int:orientacao_id>")
@login_required
def orientacao_detalhe(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    # a linha do tempo é apresentada na própria página do vínculo; o filtro por
    # tipo recarrega esta página com ?tipo=, ancorando na seção
    tipo = request.args.get("tipo", "")
    eventos = linha_tempo.eventos(orientacao)
    if tipo in linha_tempo.TIPOS:
        eventos = [e for e in eventos if e["tipo"] == tipo]
    return render_template(
        "main/orientacao_detalhe.html",
        orientacao=orientacao,
        pode_alterar_titulo=_pode_alterar_titulo(orientacao),
        eventos=eventos,
        tipos=linha_tempo.TIPOS,
        tipo_ativo=tipo,
    )


@bp.route("/orientacoes/<int:orientacao_id>/relatorio.pdf")
@login_required
def relatorio_orientacao(orientacao_id: int):
    """Retrato consolidado do vínculo. `orientacao_autorizada` já restringe às
    partes e ao administrador."""
    orientacao = orientacao_autorizada(orientacao_id)
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="relatorio-vinculo-{orientacao.id}.pdf"'
        },
    )


@bp.route("/orientacoes/<int:orientacao_id>/titulo", methods=["GET", "POST"])
@login_required
def alterar_titulo(orientacao_id: int):
    """O orientador altera o título do projeto; a alteração é registrada como
    evento do vínculo, com o título anterior preservado. Datas de início e fim
    não são editáveis aqui — competem ao administrador."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not _pode_alterar_titulo(orientacao):
        abort(403)
    form = TituloProjetoForm(titulo_projeto=orientacao.titulo_projeto)
    if form.validate_on_submit():
        if form.titulo_projeto.data.strip() == orientacao.titulo_projeto:
            flash("O título informado é igual ao atual.", "warning")
        else:
            try:
                eventos_service.registrar_evento(
                    orientacao,
                    tipo="mudanca_titulo",
                    fundamentacao=form.fundamentacao.data,
                    usuario=current_user,
                    texto_novo=form.titulo_projeto.data.strip(),
                )
                db.session.commit()
                flash("Título do projeto alterado; o histórico foi registrado.", "success")
                return redirect(
                    url_for("main.orientacao_detalhe", orientacao_id=orientacao.id)
                )
            except EventoInvalido as exc:
                flash(str(exc), "danger")
    return render_template(
        "main/titulo_form.html", form=form, orientacao=orientacao
    )


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
