from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.cronogramas import bp
from app.blueprints.cronogramas.forms import (
    AnexoMarcoForm,
    ConfirmacaoForm,
    DevolverForm,
    MarcoForm,
    SinalizarForm,
)
from app.blueprints.documentos.forms import flags_da_natureza, restringir_natureza
from app.extensions import db
from app.models import Documento, Marco
from app.models.cronograma import ultima_versao
from app.services import auditoria
from app.services import cronogramas as servico_cronograma
from app.services.rbac import manda_no_cronograma, orientacao_autorizada
from app.services.uploads import UploadInvalido, salvar_versao


def _avisar_devolucao(declarada: bool, marco, devolvida: bool) -> None:
    """Exibe o desfecho da devolução declarada no upload (ver serviço)."""
    if declarada:
        flash(*servico_cronograma.recado_da_devolucao(marco, devolvida))


def _marco_da_orientacao(orientacao, marco_id: int) -> Marco:
    marco = db.session.get(Marco, marco_id)
    if marco is None or marco.orientacao_id != orientacao.id:
        abort(404)
    return marco


@bp.route("/")
@login_required
def listar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    marcos = orientacao.marcos.all()
    return render_template(
        "cronogramas/listar.html",
        orientacao=orientacao,
        marcos=marcos,
        confirmacao_form=ConfirmacaoForm(),
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def criar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    form = MarcoForm()
    if form.validate_on_submit():
        marco = Marco(
            orientacao_id=orientacao.id,
            titulo=form.titulo.data,
            tipo=form.tipo.data,
            descricao=form.descricao.data,
            data_prevista=form.data_prevista.data,
            etapa=form.etapa.data,
        )
        db.session.add(marco)
        db.session.flush()
        auditoria.registrar("criacao_marco", "marco", marco.id, {"titulo": marco.titulo})
        db.session.commit()
        flash("Marco criado.", "success")
        return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
    return render_template("cronogramas/form.html", form=form, orientacao=orientacao)


@bp.route("/padrao", methods=["POST"])
@login_required
def semear_padrao(orientacao_id: int):
    """Semeia o cronograma-padrão da modalidade do vínculo. Só age sobre
    cronograma vazio, para nunca duplicar marcos; as datas semeadas são sugestões
    e ficam editáveis marco a marco."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    form = ConfirmacaoForm()
    if form.validate_on_submit():
        if orientacao.marcos.count() > 0:
            flash(
                "O cronograma já tem marcos; o modelo-padrão só é aplicado a um "
                "cronograma vazio.",
                "warning",
            )
        else:
            criados = servico_cronograma.semear_cronograma(orientacao)
            if criados:
                auditoria.registrar(
                    "criacao_cronograma_padrao", "orientacao", orientacao.id,
                    {"marcos": len(criados)},
                )
                db.session.commit()
                flash(
                    f"Cronograma-padrão criado com {len(criados)} marco(s). "
                    "Ajuste as datas conforme o caso.",
                    "success",
                )
            else:
                flash("Não há modelo-padrão para esta modalidade.", "warning")
    return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))


@bp.route("/<int:marco_id>")
@login_required
def detalhe(orientacao_id: int, marco_id: int):
    """Página da tarefa: reúne descrição, entregas e reuniões ligadas, a nota do
    orientando, e as ações (anexar, sinalizar, confirmar) conforme o papel."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    anexo_form = AnexoMarcoForm(titulo=marco.titulo)
    # a versão da orientanda é sempre entrega dela: o campo some para ela. Para
    # os demais, as escolhas são as MESMAS que o POST aceita — oferecer aqui uma
    # opção que a rota recusa descartaria o upload sem explicação.
    if current_user.id == orientacao.orientando_id:
        del anexo_form.natureza
    else:
        restringir_natureza(anexo_form.natureza, manda_no_cronograma(orientacao))
    # uma passada pelas entregas serve o aviso do topo e a tabela: cada leitura
    # de `versao_atual` vai ao banco (relação dynamic)
    entregas = marco.entregas
    return render_template(
        "cronogramas/detalhe.html",
        orientacao=orientacao,
        marco=marco,
        entregas=entregas,
        ultima=ultima_versao(entregas),
        anexo_form=anexo_form,
        sinalizar_form=SinalizarForm(),
        confirmacao_form=ConfirmacaoForm(),
        devolver_form=DevolverForm(),
    )


@bp.route("/<int:marco_id>/anexar", methods=["POST"])
@login_required
def anexar(orientacao_id: int, marco_id: int):
    """Anexa um documento à tarefa: cria um documento ligado ao marco e grava a
    versão 1. Disponível a qualquer participante do vínculo, como em documentos."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = AnexoMarcoForm()
    eh_gestor = current_user.id != orientacao.orientando_id
    if not eh_gestor:
        del form.natureza
    else:
        restringir_natureza(form.natureza, manda_no_cronograma(orientacao))
    if form.validate_on_submit():
        eh_devolucao, em_nome = (
            flags_da_natureza(form.natureza.data) if eh_gestor else (False, False)
        )
        documento = Documento(
            orientacao_id=orientacao.id,
            marco_id=marco.id,
            titulo=form.titulo.data,
            criado_por=current_user.id,
        )
        db.session.add(documento)
        db.session.flush()
        try:
            versao = salvar_versao(
                documento, form.arquivo.data, current_user, form.comentario.data,
                eh_devolucao=eh_devolucao, em_nome_do_orientando=em_nome,
            )
        except UploadInvalido as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            auditoria.registrar(
                "criacao_documento", "documento", documento.id,
                {"titulo": documento.titulo, "arquivo": versao.nome_original,
                 "origem": "marco", "marco_id": marco.id, "natureza": versao.natureza},
            )
            # o comentário do upload vira a nota da devolução; o serviço recusa
            # se a entrega não estiver sinalizada
            devolvido = eh_devolucao and servico_cronograma.devolver_para_revisao(
                marco, form.comentario.data or ""
            )
            db.session.commit()
            flash("Documento anexado à tarefa (versão 1).", "success")
            _avisar_devolucao(eh_devolucao, marco, devolvido)
    else:
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )


@bp.route("/<int:marco_id>/editar", methods=["GET", "POST"])
@login_required
def editar(orientacao_id: int, marco_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = MarcoForm(obj=marco)
    if form.validate_on_submit():
        form.populate_obj(marco)
        auditoria.registrar("edicao_marco", "marco", marco.id)
        db.session.commit()
        flash("Marco atualizado.", "success")
        return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
    return render_template("cronogramas/form.html", form=form, orientacao=orientacao)


@bp.route("/<int:marco_id>/sinalizar", methods=["POST"])
@login_required
def sinalizar_conclusao(orientacao_id: int, marco_id: int):
    """Orientando sinaliza conclusão; efetivação depende do orientador."""
    orientacao = orientacao_autorizada(orientacao_id)
    if current_user.id != orientacao.orientando_id:
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = SinalizarForm()
    if form.validate_on_submit() and marco.status != "concluido":
        marco.conclusao_sinalizada = True
        marco.status = "em_andamento"
        # o reenvio fecha o ciclo da devolução: a nota do orientador descrevia
        # o que corrigir, e o que ele pediu já foi atendido. Deixá-la viva a
        # faria reaparecer sob a data da devolução seguinte.
        marco.nota_devolucao = None
        if form.nota.data:
            marco.nota_conclusao = form.nota.data
        auditoria.registrar(
            "sinalizacao_conclusao_marco", "marco", marco.id,
            {"com_nota": bool(form.nota.data)},
        )
        db.session.commit()
        flash("Conclusão sinalizada; aguardando confirmação do orientador.", "info")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )


@bp.route("/<int:marco_id>/confirmar", methods=["POST"])
@login_required
def confirmar_conclusao(orientacao_id: int, marco_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = ConfirmacaoForm()
    if form.validate_on_submit() and servico_cronograma.confirmar_conclusao(marco):
        db.session.commit()
        flash("Marco concluído.", "success")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )


@bp.route("/<int:marco_id>/devolver", methods=["POST"])
@login_required
def devolver_para_revisao(orientacao_id: int, marco_id: int):
    """Devolve a entrega ao orientando corrigir. Mesmo RBAC de `confirmar` — o
    cronograma é do orientador principal (ou admin)."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = DevolverForm()
    if form.validate_on_submit():
        if servico_cronograma.devolver_para_revisao(marco, form.nota.data):
            db.session.commit()
            flash("Entrega devolvida para revisão do orientando.", "success")
        else:
            # recusa silenciosa perderia, sem aviso, a nota que ele digitou —
            # acontece com formulário reenviado depois de a tarefa já ter sido
            # devolvida ou concluída noutra aba
            flash(
                *servico_cronograma.recado_da_devolucao(
                    marco, False, com_versao=False
                )
            )
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )
