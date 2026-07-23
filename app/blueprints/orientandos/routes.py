from flask import flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.orientandos import bp
from app.blueprints.orientandos.forms import OrientandoForm
from app.extensions import db
from app.models import Orientacao, Usuario
from app.services import credenciais
from app.services.rbac import role_required
from app.services.usuarios import (
    GestaoUsuarioInvalida,
    criar_orientando_com_vinculo,
)


def _meus_orientandos():
    """Orientandos vinculados ao orientador corrente ou criados por ele."""
    vinculados = (
        Usuario.query.join(Orientacao, Orientacao.orientando_id == Usuario.id)
        .filter(Orientacao.orientador_id == current_user.id)
    )
    criados = Usuario.query.filter_by(papel="orientando", criado_por=current_user.id)
    return vinculados.union(criados).order_by(Usuario.nome).all()


@bp.route("/")
@role_required("orientador")
def listar():
    orientandos = _meus_orientandos()
    vinculos = {
        o.orientando_id: o
        for o in Orientacao.query.filter_by(
            orientador_id=current_user.id, status="ativa"
        )
    }
    return render_template(
        "orientandos/listar.html", orientandos=orientandos, vinculos=vinculos
    )


@bp.route("/novo", methods=["GET", "POST"])
@role_required("orientador")
def criar():
    form = OrientandoForm()
    if form.validate_on_submit():
        try:
            orientacao, senha = criar_orientando_com_vinculo(
                nome=form.nome.data,
                email=form.email.data.lower().strip(),
                orientador=current_user,
                modalidade=form.modalidade.data,
                titulo_projeto=form.titulo_projeto.data,
                data_inicio=form.data_inicio.data,
                data_fim_prevista=form.data_fim_prevista.data,
                telefone=form.telefone.data,
            )
            db.session.commit()
            flash(
                "Orientando criado e vínculo de orientação atribuído a você.",
                "success",
            )
            # depois do commit: falar com o SMTP dentro da transação seguraria
            # a trava de escrita do SQLite
            orientando = orientacao.orientando
            enviado = credenciais.enviar(orientando, senha, "criacao")
            db.session.commit()
            if not enviado:
                # renderiza em vez de redirecionar com flash: a mensagem de
                # flash viaja na sessão, um cookie assinado mas não cifrado
                return render_template(
                    "admin/senha_gerada.html",
                    usuario=orientando,
                    senha=senha,
                    motivo=credenciais.motivo_de_falha(),
                    voltar_url=url_for("orientandos.listar"),
                )
            flash(credenciais.mensagem_de_sucesso(orientando), "success")
            return redirect(url_for("orientandos.listar"))
        except GestaoUsuarioInvalida as exc:
            flash(str(exc), "danger")
    return render_template("orientandos/form.html", form=form)


# Exclusão e desativação de contas competem exclusivamente ao administrador
# (decisão de 20/07/2026): o orientador cria a conta e o vínculo, mas não os
# remove. A rota de exclusão que existia aqui foi retirada.
