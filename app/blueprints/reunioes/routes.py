from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.blueprints.cronogramas.forms import MarcoForm
from app.blueprints.reunioes import bp
from app.blueprints.reunioes.forms import (
    AgendarReuniaoForm,
    AtaGrupoForm,
    CancelarReuniaoForm,
    ConvidadosForm,
    MarcoGrupoForm,
)
from app.extensions import db
from app.models import Ata, AtaParticipacao, Marco, Orientacao
from app.services import auditoria, convites, tarefas
from app.services.atas import (
    AtaImutavel,
    OperacaoInvalida,
    agendar_reuniao,
    alterar_convidados,
    cancelar_reuniao,
    excluir_reuniao,
)
from app.services.rbac import role_required


def _vinculos_ativos():
    return (
        Orientacao.query.filter_by(orientador_id=current_user.id, status="ativa")
        .order_by(Orientacao.titulo_projeto)
        .all()
    )


def _choices(vinculos):
    return [(o.id, f"{o.orientando.nome} ({o.titulo_projeto})") for o in vinculos]


def _reuniao_do_orientador(ata_id: int) -> Ata:
    """Reunião convocada pelo orientador corrente. 404 se não existe ou é de
    outro, pelo mesmo critério de `_marcos_do_grupo`: a autorização é ter
    convocado, e revelar a existência do registro alheio já seria informação.

    Sem exceção para o administrador, porque este blueprint inteiro é do
    orientador (`role_required("orientador")`, em que admin não é implícito). A
    agenda é pessoal; o admin chega ao registro pelo módulo de atas do vínculo,
    que é o caminho previsto para ele."""
    ata = db.session.get(Ata, ata_id)
    if ata is None or ata.orientador_id != current_user.id:
        abort(404)
    return ata


def _avisar(ata: Ata, evento: str, retirados=None) -> None:
    """Notifica os convidados e informa o resultado na tela.

    Chamado **depois** do commit da rota: falar com o SMTP dentro da transação
    seguraria a trava de escrita do SQLite. O registro do envio é confirmado em
    transação própria, que não pode arrastar a operação já concluída."""
    entregues, falhas = convites.notificar(ata, evento, retirados)
    db.session.commit()
    texto, categoria = convites.mensagem_de_resultado(entregues, falhas)
    flash(texto, categoria)


def _marcos_do_grupo(grupo_id: str) -> list:
    """Marcos de uma tarefa em grupo, restritos aos vínculos do orientador
    corrente, que é a autorização, já que a tarefa não tem dono próprio no
    esquema. 404 se o grupo não existe ou não é dele."""
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
    """Agenda do orientador: o ciclo inteiro de cada reunião numa tela só.

    A separação é por estado, não por tipo: o que interessa a quem abre esta
    página é o que exige ação dele agora (redigir a ata do que já ocorreu) e o
    que vem pela frente."""
    vinculos = _vinculos_ativos()
    reunioes = (
        Ata.query.filter_by(orientador_id=current_user.id)
        .order_by(Ata.data_reuniao.desc())
        .all()
    )
    return render_template(
        "reunioes/index.html",
        vinculos=vinculos,
        proximas=sorted(
            (a for a in reunioes if a.agendada), key=lambda a: a.data_reuniao
        ),
        aguardando_ata=[a for a in reunioes if a.realizada and not a.ata_redigida],
        em_redacao=[a for a in reunioes if a.realizada and a.ata_redigida],
        encerradas=[a for a in reunioes if a.status == "finalizada"],
        canceladas=[a for a in reunioes if a.status == "cancelada"],
        tarefas_grupo=_tarefas_em_grupo(),
        cancelar_form=CancelarReuniaoForm(),
    )


# ---------------------------------------------------------------------------
# Ciclo da reunião: agendar, alterar convidados, cancelar, excluir


@bp.route("/agendar", methods=["GET", "POST"])
@role_required("orientador")
def agendar():
    vinculos = _vinculos_ativos()
    form = AgendarReuniaoForm()
    form.orientacoes.choices = _choices(vinculos)
    if form.validate_on_submit():
        selecionadas = [o for o in vinculos if o.id in form.orientacoes.data]
        try:
            ata = agendar_reuniao(
                current_user,
                vinculos=selecionadas,
                data=form.data_reuniao.data,
                hora=form.hora_reuniao.data,
                pauta=form.pauta.data,
                link=form.link_reuniao.data,
            )
        except OperacaoInvalida as exc:
            flash(str(exc), "danger")
            return render_template(
                "reunioes/agendar.html", form=form, vinculos=vinculos
            )
        db.session.commit()
        flash(
            f"Reunião agendada para {ata.data_reuniao.strftime('%d/%m/%Y')} "
            f"com {len(selecionadas)} convidado(s).",
            "success",
        )
        _avisar(ata, "agendada")
        return redirect(url_for("reunioes.index"))
    return render_template("reunioes/agendar.html", form=form, vinculos=vinculos)


@bp.route("/<int:ata_id>/convidados", methods=["GET", "POST"])
@role_required("orientador")
def convidados(ata_id: int):
    ata = _reuniao_do_orientador(ata_id)
    vinculos = _vinculos_ativos()
    # os já convidados entram nas opções mesmo que o vínculo tenha sido
    # encerrado desde então: retirá-los da lista os removeria em silêncio
    ja = [o for o in ata.orientacoes if o not in vinculos]
    disponiveis = vinculos + ja

    form = ConvidadosForm(orientacoes=[o.id for o in ata.orientacoes])
    form.orientacoes.choices = _choices(disponiveis)
    if form.validate_on_submit():
        selecionadas = [o for o in disponiveis if o.id in form.orientacoes.data]
        try:
            incluidos, excluidos = alterar_convidados(ata, selecionadas)
        except (AtaImutavel, OperacaoInvalida) as exc:
            db.session.commit()  # persiste o log da tentativa
            flash(str(exc), "danger")
            return redirect(url_for("reunioes.index"))
        # guardados antes do commit: depois dele já não constam da reunião, e
        # quem foi desconvidado é justamente quem precisa saber
        retirados = [o for o in disponiveis if o.id in excluidos]
        db.session.commit()
        if not incluidos and not excluidos:
            flash("Nenhuma alteração na lista de convidados.", "info")
            return redirect(url_for("reunioes.index"))
        flash(
            f"Convidados atualizados: {len(incluidos)} incluído(s), "
            f"{len(excluidos)} retirado(s).",
            "success",
        )
        _avisar(ata, "convidados_alterados", retirados=retirados)
        return redirect(url_for("reunioes.index"))
    return render_template(
        "reunioes/convidados.html", form=form, ata=ata, vinculos=disponiveis
    )


@bp.route("/<int:ata_id>/cancelar", methods=["POST"])
@role_required("orientador")
def cancelar(ata_id: int):
    ata = _reuniao_do_orientador(ata_id)
    form = CancelarReuniaoForm()
    if not form.validate_on_submit():
        flash("Informe o motivo do cancelamento.", "danger")
        return redirect(url_for("reunioes.index"))
    try:
        cancelar_reuniao(ata, current_user, form.motivo.data)
    except (AtaImutavel, OperacaoInvalida) as exc:
        db.session.commit()  # persiste o log da tentativa
        flash(str(exc), "danger")
        return redirect(url_for("reunioes.index"))
    db.session.commit()
    flash("Reunião cancelada. O registro e o motivo ficam no histórico.", "success")
    _avisar(ata, "cancelada")
    return redirect(url_for("reunioes.index"))


@bp.route("/<int:ata_id>/excluir", methods=["POST"])
@role_required("orientador")
def excluir(ata_id: int):
    ata = _reuniao_do_orientador(ata_id)
    try:
        excluir_reuniao(ata)
    except (AtaImutavel, OperacaoInvalida) as exc:
        db.session.commit()  # persiste o log da tentativa
        flash(str(exc), "danger")
        return redirect(url_for("reunioes.index"))
    db.session.commit()
    flash("Reunião excluída.", "success")
    return redirect(url_for("reunioes.index"))


@bp.route("/<int:ata_id>/tarefas/nova", methods=["GET", "POST"])
@role_required("orientador")
def criar_tarefa_derivada(ata_id: int):
    """Tarefa que nasce do que foi decidido na reunião.

    Os convidados vêm pré-marcados e o marco criado fica ligado à ata, de modo
    que a derivação apareça no cronograma, na linha do tempo e no próprio
    registro da reunião."""
    ata = _reuniao_do_orientador(ata_id)
    # ligar um marco novo à ata altera os marcos discutidos, que a finalização
    # congela; a cancelada, por sua vez, não deriva coisa alguma
    if ata.imutavel:
        auditoria.registrar("tentativa_edicao_ata_finalizada", "ata", ata.id)
        db.session.commit()
        flash(
            "Reunião encerrada ou cancelada não deriva tarefas. Atribua a "
            "tarefa pela tela de Reuniões.",
            "warning",
        )
        return redirect(url_for("reunioes.index"))

    participantes = list(ata.orientacoes)
    form = MarcoGrupoForm(orientacoes=[o.id for o in participantes])
    form.orientacoes.choices = _choices(participantes)
    if form.validate_on_submit():
        selecionadas = [o for o in participantes if o.id in form.orientacoes.data]
        criados = tarefas.criar_tarefa(
            selecionadas,
            titulo=form.titulo.data,
            tipo=form.tipo.data,
            descricao=form.descricao.data,
            data_prevista=form.data_prevista.data,
            etapa=form.etapa.data,
            ata=ata,
        )
        db.session.commit()
        flash(
            f"Tarefa derivada da reunião e atribuída a {len(criados)} "
            f"orientando(s).",
            "success",
        )
        return redirect(url_for("reunioes.index"))
    return render_template(
        "reunioes/tarefa_derivada.html", form=form, ata=ata, vinculos=participantes
    )


# ---------------------------------------------------------------------------
# Tarefas em grupo


@bp.route("/tarefas/<grupo_id>/editar", methods=["GET", "POST"])
@role_required("orientador")
def editar_tarefa_grupo(grupo_id: str):
    """Edita a tarefa em grupo, propagando o conteúdo a todos os marcos do
    grupo. Status e conclusão de cada um seguem individuais: um orientando
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
    histórico, mesmo critério das contas: preserva-se o que já produziu
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
    """Registro retroativo de reunião já ocorrida: a ata é redigida de uma vez.

    Não dispara convite, pelo motivo evidente. Reunião a realizar entra por
    `agendar`."""
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
        tarefas.criar_tarefa(
            selecionadas,
            titulo=form.titulo.data,
            tipo=form.tipo.data,
            descricao=form.descricao.data,
            data_prevista=form.data_prevista.data,
            etapa=form.etapa.data,
        )
        db.session.commit()
        flash(
            f"Tarefa atribuída a {len(selecionadas)} orientando(s) "
            f"(um marco por cronograma).",
            "success",
        )
        return redirect(url_for("reunioes.index"))
    return render_template("reunioes/tarefa_form.html", form=form, vinculos=vinculos)
