import uuid

from flask import flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.reunioes import bp
from app.blueprints.reunioes.forms import AtaGrupoForm, MarcoGrupoForm
from app.extensions import db
from app.models import Ata, AtaParticipacao, Marco, Orientacao
from app.models.cronograma import tipo_do_marco
from app.services import auditoria
from app.services.rbac import role_required


def _vinculos_ativos():
    return (
        Orientacao.query.filter_by(orientador_id=current_user.id, status="ativa")
        .order_by(Orientacao.titulo_projeto)
        .all()
    )


def _choices(vinculos):
    return [(o.id, f"{o.orientando.nome} — {o.titulo_projeto}") for o in vinculos]


@bp.route("/")
@role_required("orientador")
def index():
    vinculos = _vinculos_ativos()
    atas_grupo = (
        Ata.query.filter_by(orientador_id=current_user.id, tipo="grupo")
        .order_by(Ata.data_reuniao.desc())
        .all()
    )
    return render_template(
        "reunioes/index.html", vinculos=vinculos, atas_grupo=atas_grupo
    )


@bp.route("/atas/nova", methods=["GET", "POST"])
@role_required("orientador")
def criar_ata_grupo():
    vinculos = _vinculos_ativos()
    form = AtaGrupoForm()
    form.orientacoes.choices = _choices(vinculos)
    if form.validate_on_submit():
        selecionadas = [o for o in vinculos if o.id in form.orientacoes.data]
        ata = Ata(
            # com um único orientando a reunião é individual; o registro fica
            # idêntico ao criado pelo módulo do próprio vínculo
            tipo="grupo" if len(selecionadas) > 1 else "individual",
            orientador_id=current_user.id,
            data_reuniao=form.data_reuniao.data,
            hora_reuniao=form.hora_reuniao.data,
            pauta=form.pauta.data,
            deliberacoes=form.deliberacoes.data,
            redigida_por=current_user.id,
            participacoes=[
                AtaParticipacao(orientacao_id=o.id) for o in selecionadas
            ],
        )
        db.session.add(ata)
        db.session.flush()
        auditoria.registrar(
            "criacao_ata_grupo" if ata.tipo == "grupo" else "criacao_ata",
            "ata",
            ata.id,
            {"orientacoes": [o.id for o in selecionadas]},
        )
        db.session.commit()
        flash(
            f"Ata de reunião registrada como rascunho "
            f"({len(selecionadas)} vínculo(s)).",
            "success",
        )
        return redirect(url_for("reunioes.index"))
    return render_template("reunioes/ata_form.html", form=form, vinculos=vinculos)


@bp.route("/tarefas/nova", methods=["GET", "POST"])
@role_required("orientador")
def criar_tarefa_grupo():
    vinculos = _vinculos_ativos()
    form = MarcoGrupoForm()
    form.orientacoes.choices = _choices(vinculos)
    if form.validate_on_submit():
        selecionadas = [o for o in vinculos if o.id in form.orientacoes.data]
        # identificador de origem comum apenas quando a tarefa é coletiva
        grupo_id = uuid.uuid4().hex if len(selecionadas) > 1 else None
        for orientacao in selecionadas:
            marco = Marco(
                orientacao_id=orientacao.id,
                titulo=form.titulo.data,
                tipo=tipo_do_marco(form.tipo.data, form.etapa.data),
                descricao=form.descricao.data,
                data_prevista=form.data_prevista.data,
                etapa=form.etapa.data,
                grupo_id=grupo_id,
            )
            db.session.add(marco)
        auditoria.registrar(
            "criacao_marco_grupo" if grupo_id else "criacao_marco",
            "marco",
            None,
            {
                "grupo_id": grupo_id,
                "titulo": form.titulo.data,
                "orientacoes": [o.id for o in selecionadas],
            },
        )
        db.session.commit()
        flash(
            f"Tarefa atribuída a {len(selecionadas)} orientando(s) "
            f"(um marco por cronograma).",
            "success",
        )
        return redirect(url_for("reunioes.index"))
    return render_template("reunioes/tarefa_form.html", form=form, vinculos=vinculos)
