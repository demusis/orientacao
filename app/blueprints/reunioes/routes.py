import uuid

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.cronogramas.forms import MarcoForm
from app.blueprints.reunioes import bp
from app.blueprints.reunioes.forms import AtaGrupoForm, MarcoGrupoForm
from app.extensions import db
from app.models import Ata, AtaParticipacao, Marco, Orientacao
from app.services import auditoria
from app.services.rbac import role_required


def _vinculos_ativos():
    return (
        Orientacao.query.filter_by(orientador_id=current_user.id, status="ativa")
        .order_by(Orientacao.titulo_projeto)
        .all()
    )


def _choices(vinculos):
    return [(o.id, f"{o.orientando.nome} ({o.titulo_projeto})") for o in vinculos]


def _marcos_do_grupo(grupo_id: str) -> list:
    """Marcos de uma tarefa em grupo, restritos aos vínculos do orientador
    corrente — a autorização, já que a tarefa não tem dono próprio no esquema.
    404 se o grupo não existe ou não é dele."""
    marcos = (
        Marco.query.join(Orientacao, Orientacao.id == Marco.orientacao_id)
        .filter(Marco.grupo_id == grupo_id, Orientacao.orientador_id == current_user.id)
        .all()
    )
    if not marcos:
        abort(404)
    return marcos


def _tarefas_em_grupo() -> list:
    """Tarefas coletivas do orientador, agrupadas por grupo_id. Uma linha por
    tarefa, com o conjunto de orientandos e um resumo de conclusão."""
    marcos = (
        Marco.query.join(Orientacao, Orientacao.id == Marco.orientacao_id)
        .filter(
            Orientacao.orientador_id == current_user.id,
            Marco.grupo_id.isnot(None),
        )
        .order_by(Marco.data_prevista.desc())
        .all()
    )
    grupos = {}
    for m in marcos:
        g = grupos.setdefault(m.grupo_id, {
            "grupo_id": m.grupo_id,
            "titulo": m.titulo,
            "data_prevista": m.data_prevista,
            "etapa": m.etapa,
            "marcos": [],
        })
        g["marcos"].append(m)
    return list(grupos.values())


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
        "reunioes/index.html",
        vinculos=vinculos,
        atas_grupo=atas_grupo,
        tarefas_grupo=_tarefas_em_grupo(),
    )


@bp.route("/tarefas/<grupo_id>/editar", methods=["GET", "POST"])
@role_required("orientador")
def editar_tarefa_grupo(grupo_id: str):
    """Edita a tarefa em grupo, propagando o conteúdo a todos os marcos do
    grupo. Status e conclusão de cada um seguem individuais — um orientando
    conclui, outro não."""
    marcos = _marcos_do_grupo(grupo_id)
    form = MarcoForm(obj=marcos[0])  # todos compartilham o conteúdo
    if form.validate_on_submit():
        for m in marcos:
            m.titulo = form.titulo.data
            m.tipo = form.tipo.data
            m.descricao = form.descricao.data
            m.data_prevista = form.data_prevista.data
            m.etapa = form.etapa.data
        auditoria.registrar(
            "edicao_marco_grupo", "marco", marcos[0].id,
            {"grupo_id": grupo_id, "marcos": [m.id for m in marcos]},
        )
        db.session.commit()
        flash(f"Tarefa atualizada em {len(marcos)} cronograma(s).", "success")
        return redirect(url_for("reunioes.index"))
    return render_template(
        "reunioes/tarefa_editar.html", form=form, marcos=marcos, grupo_id=grupo_id
    )


@bp.route("/tarefas/<grupo_id>/excluir", methods=["POST"])
@role_required("orientador")
def excluir_tarefa_grupo(grupo_id: str):
    """Exclui a tarefa em grupo. Recusada se QUALQUER marco do grupo tem
    histórico — mesmo critério das contas: preserva-se o que já produziu
    registro, apaga-se apenas o que ainda está limpo."""
    marcos = _marcos_do_grupo(grupo_id)
    com_historico = [m for m in marcos if m.tem_historico]
    if com_historico:
        auditoria.registrar(
            "exclusao_tarefa_recusada", "marco", marcos[0].id,
            {"grupo_id": grupo_id, "com_historico": [m.id for m in com_historico]},
        )
        db.session.commit()
        flash(
            "Exclusão recusada: a tarefa já tem histórico em ao menos um "
            "orientando (conclusão sinalizada, documento entregue ou reunião que "
            "a discutiu). Edite-a, ou trate cada cronograma individualmente.",
            "danger",
        )
        return redirect(url_for("reunioes.index"))

    ids = [m.id for m in marcos]
    for m in marcos:
        db.session.delete(m)
    auditoria.registrar(
        "exclusao_tarefa_grupo", "marco", ids[0],
        {"grupo_id": grupo_id, "marcos": ids},
    )
    db.session.commit()
    flash(f"Tarefa excluída de {len(ids)} cronograma(s).", "success")
    return redirect(url_for("reunioes.index"))


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
        criados = []
        for orientacao in selecionadas:
            marco = Marco(
                orientacao_id=orientacao.id,
                titulo=form.titulo.data,
                tipo=form.tipo.data,
                descricao=form.descricao.data,
                data_prevista=form.data_prevista.data,
                etapa=form.etapa.data,
                grupo_id=grupo_id,
            )
            db.session.add(marco)
            criados.append(marco)
        # um registro para N marcos: entidade_id fica no primeiro e a lista
        # completa nos dados, para que o log seja correlacionável
        db.session.flush()
        auditoria.registrar(
            "criacao_marco_grupo" if grupo_id else "criacao_marco",
            "marco",
            criados[0].id if criados else None,
            {
                "grupo_id": grupo_id,
                "titulo": form.titulo.data,
                "marcos": [m.id for m in criados],
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
