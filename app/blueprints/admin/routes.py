from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.admin import bp
from app.blueprints.admin.forms import (
    EncerrarOrientacaoForm,
    OrientacaoForm,
    UsuarioForm,
)
from app.extensions import db
from app.models import Orientacao, Usuario
from app.services import auditoria
from app.services.rbac import role_required


@bp.route("/usuarios")
@role_required("admin")
def listar_usuarios():
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    return render_template("admin/usuarios.html", usuarios=usuarios)


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@role_required("admin")
def criar_usuario():
    form = UsuarioForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if Usuario.query.filter_by(email=email).first():
            flash("E-mail já cadastrado.", "danger")
        elif not form.senha.data:
            flash("Senha inicial é obrigatória na criação.", "danger")
        else:
            usuario = Usuario(
                nome=form.nome.data,
                email=email,
                papel=form.papel.data,
                ativo=form.ativo.data,
            )
            usuario.set_senha(form.senha.data)
            db.session.add(usuario)
            db.session.flush()
            auditoria.registrar(
                "criacao_usuario", "usuario", usuario.id, {"email": email, "papel": usuario.papel}
            )
            db.session.commit()
            flash("Usuário criado.", "success")
            return redirect(url_for("admin.listar_usuarios"))
    return render_template("admin/usuario_form.html", form=form, titulo="Novo usuário")


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


@bp.route("/auditoria")
@role_required("admin")
def listar_auditoria():
    from app.models import LogAuditoria

    logs = LogAuditoria.query.order_by(LogAuditoria.timestamp.desc()).limit(200).all()
    return render_template("admin/auditoria.html", logs=logs)
