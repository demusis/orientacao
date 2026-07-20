from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.admin import bp
from app.blueprints.admin.forms import (
    AjusteDatasForm,
    CoorientadorForm,
    EncerrarOrientacaoForm,
    EventoVinculoForm,
    ExcluirForm,
    FiltroAuditoriaForm,
    OrientacaoForm,
    RemoverForm,
    UsuarioForm,
)
from app.services import eventos as eventos_service
from app.services.eventos import EventoInvalido
from app.extensions import db
from app.models import Orientacao, OrientacaoOrientador, Usuario
from app.services import auditoria
from app.services import usuarios as usuarios_service
from app.services.rbac import role_required
from app.services.usuarios import GestaoUsuarioInvalida


@bp.route("/usuarios")
@role_required("admin")
def listar_usuarios():
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    return render_template(
        "admin/usuarios.html", usuarios=usuarios, excluir_form=ExcluirForm()
    )


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@role_required("admin")
def criar_usuario():
    form = UsuarioForm()
    if form.validate_on_submit():
        if not form.senha.data:
            flash("Senha inicial é obrigatória na criação.", "danger")
        else:
            try:
                usuarios_service.criar_usuario(
                    nome=form.nome.data,
                    email=form.email.data.lower().strip(),
                    papel=form.papel.data,
                    senha=form.senha.data,
                    autor=current_user,
                    ativo=form.ativo.data,
                )
                db.session.commit()
                flash("Usuário criado.", "success")
                return redirect(url_for("admin.listar_usuarios"))
            except GestaoUsuarioInvalida as exc:
                flash(str(exc), "danger")
    return render_template("admin/usuario_form.html", form=form, titulo="Novo usuário")


@bp.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@role_required("admin")
def excluir_usuario(usuario_id: int):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    form = ExcluirForm()
    if form.validate_on_submit():
        try:
            # vínculos ainda sem qualquer registro são removidos com a conta;
            # do contrário nenhuma conta de orientando seria excluível, pois o
            # vínculo passou a nascer junto com ela
            usuarios_service.excluir_usuario(
                usuario,
                current_user,
                usuarios_service.vinculos_descartaveis(usuario),
            )
            db.session.commit()
            flash("Usuário excluído.", "success")
        except GestaoUsuarioInvalida as exc:
            db.session.commit()  # persiste o log da recusa
            flash(str(exc), "danger")
    return redirect(url_for("admin.listar_usuarios"))


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@role_required("admin")
def editar_usuario(usuario_id: int):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    form = UsuarioForm(obj=usuario)
    if form.validate_on_submit():
        despromocao = (
            usuario.papel == "admin"
            and usuario.ativo
            and (form.papel.data != "admin" or not form.ativo.data)
        )
        if despromocao and usuario.id == current_user.id:
            auditoria.registrar("autodespromocao_recusada", "usuario", usuario.id)
            db.session.commit()
            flash(
                "Um administrador não pode alterar o próprio papel nem desativar a própria conta.",
                "danger",
            )
            return redirect(url_for("admin.editar_usuario", usuario_id=usuario.id))
        if despromocao and Usuario.query.filter_by(papel="admin", ativo=True).count() <= 1:
            auditoria.registrar("despromocao_ultimo_admin_recusada", "usuario", usuario.id)
            db.session.commit()
            flash(
                "Operação recusada: o sistema deve manter ao menos um administrador ativo.",
                "danger",
            )
            return redirect(url_for("admin.editar_usuario", usuario_id=usuario.id))
        usuario.nome = form.nome.data
        usuario.email = form.email.data.lower().strip()
        usuario.papel = form.papel.data
        usuario.ativo = form.ativo.data
        if form.senha.data:
            usuario.set_senha(form.senha.data)
        auditoria.registrar(
            "edicao_usuario", "usuario", usuario.id, {"papel": usuario.papel, "ativo": usuario.ativo}
        )
        db.session.commit()
        flash("Usuário atualizado.", "success")
        return redirect(url_for("admin.listar_usuarios"))
    return render_template("admin/usuario_form.html", form=form, titulo="Editar usuário")


@bp.route("/orientacoes")
@role_required("admin")
def listar_orientacoes():
    orientacoes = Orientacao.query.order_by(Orientacao.criado_em.desc()).all()
    return render_template("admin/orientacoes.html", orientacoes=orientacoes)


@bp.route("/orientacoes/nova", methods=["GET", "POST"])
@role_required("admin")
def criar_orientacao():
    form = OrientacaoForm()
    form.orientador_id.choices = [
        (u.id, u.nome)
        for u in Usuario.query.filter_by(papel="orientador", ativo=True).order_by(Usuario.nome)
    ]
    form.orientando_id.choices = [
        (u.id, u.nome)
        for u in Usuario.query.filter_by(papel="orientando", ativo=True).order_by(Usuario.nome)
    ]
    if form.validate_on_submit():
        ja_ativa = Orientacao.query.filter_by(
            orientador_id=form.orientador_id.data,
            orientando_id=form.orientando_id.data,
            status="ativa",
        ).first()
        if ja_ativa:
            flash("Já existe vínculo ativo entre este orientador e orientando.", "danger")
        else:
            orientacao = Orientacao(
                orientador_id=form.orientador_id.data,
                orientando_id=form.orientando_id.data,
                modalidade=form.modalidade.data,
                titulo_projeto=form.titulo_projeto.data,
                data_inicio=form.data_inicio.data,
                data_fim_prevista=form.data_fim_prevista.data,
            )
            db.session.add(orientacao)
            db.session.flush()
            auditoria.registrar(
                "criacao_orientacao",
                "orientacao",
                orientacao.id,
                {
                    "orientador_id": orientacao.orientador_id,
                    "orientando_id": orientacao.orientando_id,
                    "modalidade": orientacao.modalidade,
                },
            )
            db.session.commit()
            flash("Vínculo de orientação criado.", "success")
            return redirect(url_for("admin.listar_orientacoes"))
    return render_template("admin/orientacao_form.html", form=form)


@bp.route("/orientacoes/<int:orientacao_id>/encerrar", methods=["GET", "POST"])
@role_required("admin")
def encerrar_orientacao(orientacao_id: int):
    orientacao = db.session.get(Orientacao, orientacao_id) or abort(404)
    form = EncerrarOrientacaoForm()
    if form.validate_on_submit():
        anterior = orientacao.status
        orientacao.status = form.status.data
        auditoria.registrar(
            "alteracao_status_orientacao",
            "orientacao",
            orientacao.id,
            {"de": anterior, "para": orientacao.status},
        )
        db.session.commit()
        flash("Status atualizado.", "success")
        return redirect(url_for("admin.listar_orientacoes"))
    return render_template(
        "admin/orientacao_encerrar.html", form=form, orientacao=orientacao
    )


@bp.route("/orientacoes/<int:orientacao_id>/datas", methods=["GET", "POST"])
@role_required("admin")
def ajustar_datas(orientacao_id: int):
    """Alteração das datas de início e fim do projeto — privativa do
    administrador; o orientador altera apenas o título."""
    orientacao = db.session.get(Orientacao, orientacao_id) or abort(404)
    form = AjusteDatasForm(obj=orientacao)
    if form.validate_on_submit():
        anterior = {
            "data_inicio": str(orientacao.data_inicio),
            "data_fim_prevista": str(orientacao.data_fim_prevista or ""),
        }
        orientacao.data_inicio = form.data_inicio.data
        orientacao.data_fim_prevista = form.data_fim_prevista.data
        auditoria.registrar(
            "ajuste_datas_orientacao",
            "orientacao",
            orientacao.id,
            {
                "de": anterior,
                "para": {
                    "data_inicio": str(orientacao.data_inicio),
                    "data_fim_prevista": str(orientacao.data_fim_prevista or ""),
                },
            },
        )
        db.session.commit()
        flash("Datas do vínculo atualizadas.", "success")
        return redirect(url_for("admin.listar_orientacoes"))
    return render_template(
        "admin/datas_form.html", form=form, orientacao=orientacao
    )


@bp.route("/orientacoes/<int:orientacao_id>/coorientadores", methods=["GET", "POST"])
@role_required("admin")
def coorientadores(orientacao_id: int):
    orientacao = db.session.get(Orientacao, orientacao_id) or abort(404)
    ja_designados = {a.usuario_id for a in orientacao.equipe} | {
        orientacao.orientador_id
    }
    elegiveis = (
        Usuario.query.filter_by(papel="orientador", ativo=True)
        .filter(~Usuario.id.in_(ja_designados))
        .order_by(Usuario.nome)
        .all()
    )
    form = CoorientadorForm()
    form.usuario_id.choices = [(u.id, u.nome) for u in elegiveis]
    if form.validate_on_submit():
        db.session.add(
            OrientacaoOrientador(
                orientacao_id=orientacao.id,
                usuario_id=form.usuario_id.data,
                funcao="coorientador",
            )
        )
        auditoria.registrar(
            "designacao_coorientador",
            "orientacao",
            orientacao.id,
            {"usuario_id": form.usuario_id.data},
        )
        db.session.commit()
        flash("Coorientador designado.", "success")
        return redirect(
            url_for("admin.coorientadores", orientacao_id=orientacao.id)
        )
    return render_template(
        "admin/coorientadores.html",
        orientacao=orientacao,
        form=form,
        remover_form=RemoverForm(),
    )


@bp.route(
    "/orientacoes/<int:orientacao_id>/coorientadores/<int:usuario_id>/remover",
    methods=["POST"],
)
@role_required("admin")
def remover_coorientador(orientacao_id: int, usuario_id: int):
    orientacao = db.session.get(Orientacao, orientacao_id) or abort(404)
    assoc = next(
        (
            a
            for a in orientacao.equipe
            if a.usuario_id == usuario_id and a.funcao == "coorientador"
        ),
        None,
    )
    if assoc is None:
        abort(404)
    form = RemoverForm()
    if form.validate_on_submit():
        db.session.delete(assoc)
        auditoria.registrar(
            "remocao_coorientador",
            "orientacao",
            orientacao.id,
            {"usuario_id": usuario_id},
        )
        db.session.commit()
        flash("Coorientador removido.", "success")
    return redirect(url_for("admin.coorientadores", orientacao_id=orientacao.id))


@bp.route("/orientacoes/<int:orientacao_id>/eventos", methods=["GET", "POST"])
@role_required("admin")
def eventos_orientacao(orientacao_id: int):
    orientacao = db.session.get(Orientacao, orientacao_id) or abort(404)
    form = EventoVinculoForm()
    if form.validate_on_submit():
        try:
            eventos_service.registrar_evento(
                orientacao,
                tipo=form.tipo.data,
                fundamentacao=form.fundamentacao.data,
                usuario=current_user,
                data_nova=form.data_nova.data,
                texto_novo=form.texto_novo.data or None,
            )
            db.session.commit()
            flash("Evento registrado e aplicado ao vínculo.", "success")
            return redirect(
                url_for("admin.eventos_orientacao", orientacao_id=orientacao.id)
            )
        except EventoInvalido as exc:
            flash(str(exc), "danger")
    return render_template(
        "admin/eventos.html", orientacao=orientacao, form=form
    )


LIMITE_AUDITORIA = 20


@bp.route("/auditoria")
@role_required("admin")
def listar_auditoria():
    from app.models import LogAuditoria

    form = FiltroAuditoriaForm(formdata=request.args)
    form.usuario_id.choices = [(0, "— todos —")] + [
        (u.id, u.nome) for u in Usuario.query.order_by(Usuario.nome)
    ]
    acoes = [
        a
        for (a,) in db.session.query(LogAuditoria.acao)
        .distinct()
        .order_by(LogAuditoria.acao)
    ]
    form.acao.choices = [("", "— todas —")] + [(a, a) for a in acoes]

    consulta = LogAuditoria.query
    if form.validate():
        if form.de.data:
            consulta = consulta.filter(LogAuditoria.timestamp >= form.de.data)
        if form.ate.data:
            consulta = consulta.filter(LogAuditoria.timestamp <= form.ate.data)
        if form.usuario_id.data:
            consulta = consulta.filter(LogAuditoria.usuario_id == form.usuario_id.data)
        if form.acao.data:
            consulta = consulta.filter(LogAuditoria.acao == form.acao.data)

    # parâmetros de filtro repassados aos links de página; 'pagina' fica de fora
    # para não se acumular, e valores vazios são descartados para encurtar a URL
    filtros = {
        chave: valor
        for chave, valor in request.args.items()
        if chave not in ("pagina", "submit") and valor
    }
    pagina = max(1, request.args.get("pagina", 1, type=int))
    paginacao = consulta.order_by(LogAuditoria.timestamp.desc()).paginate(
        page=pagina, per_page=LIMITE_AUDITORIA, error_out=False
    )
    # página além do fim (filtro estreitado, por exemplo): leva à última existente
    if paginacao.pages and pagina > paginacao.pages:
        return redirect(
            url_for("admin.listar_auditoria", pagina=paginacao.pages, **filtros)
        )

    return render_template(
        "admin/auditoria.html",
        paginacao=paginacao,
        logs=paginacao.items,
        form=form,
        filtros=filtros,
        limite=LIMITE_AUDITORIA,
    )
