from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.cronogramas import bp
from app.blueprints.cronogramas.forms import (
    NOVO_DOCUMENTO,
    ConfirmacaoForm,
    DevolverForm,
    EntregaTarefaForm,
    MarcoIndividualForm,
    SinalizarForm,
)
from app.blueprints.documentos.forms import eh_entrega_da_orientanda
from app.extensions import db
from app.models import Documento, Marco
from app.models.cronograma import ultima_versao
from app.services import auditoria
from app.services import cronogramas as servico_cronograma
from app.services import materiais as servico_materiais
from app.services.rbac import manda_no_cronograma, orientacao_autorizada
from app.services.uploads import UploadInvalido, salvar_versao


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


def _rotulo_texto_base(documento) -> str:
    """Título com a versão atual: quem procura "a v7" acha o documento que está
    nela — a lista é de documentos, e a revisão parte da versão corrente."""
    atual = documento.versao_atual
    if atual is None:
        return documento.titulo
    return f"{documento.titulo} (hoje na v{atual.numero_versao})"


def _escolhas_texto_base(form, orientacao) -> None:
    """Os documentos do vínculo, para a tarefa de revisão apontar o texto."""
    form.documento_base_id.choices = [(0, "(nenhum)")] + [
        (d.id, _rotulo_texto_base(d))
        for d in orientacao.documentos.order_by(Documento.titulo).all()
    ]


def _aplicar_entrega_esperada(marco, form) -> None:
    """Grava o que a tarefa espera; o texto-base só vale na revisão."""
    marco.entrega_esperada = form.entrega_esperada.data or None
    marco.documento_base_id = (
        (form.documento_base_id.data or None)
        if marco.entrega_esperada == "revisao"
        else None
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def criar(orientacao_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    form = MarcoIndividualForm()
    _escolhas_texto_base(form, orientacao)
    if form.validate_on_submit():
        marco = Marco(
            orientacao_id=orientacao.id,
            titulo=form.titulo.data,
            tipo=form.tipo.data,
            descricao=form.descricao.data,
            data_prevista=form.data_prevista.data,
            etapa=form.etapa.data,
        )
        _aplicar_entrega_esperada(marco, form)
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


def _escolhas_destino(docs) -> list[tuple[str, str]]:
    """Para onde vai o envio pela tarefa: nova versão de cada documento da
    tarefa, ou um documento novo."""
    escolhas = []
    for d in docs:
        atual = d.versao_atual
        rotulo = f"Nova versão de: {d.titulo}"
        if atual is not None:
            rotulo += f" (hoje na v{atual.numero_versao})"
        escolhas.append((str(d.id), rotulo))
    escolhas.append((NOVO_DOCUMENTO, "Documento novo"))
    return escolhas


def _destino_padrao(marco, docs, ultima) -> str:
    """O destino que já vem marcado: na revisão, o texto-base; havendo
    entrega, o documento da última (corrigir é nova versão dele); senão, um
    documento novo."""
    if marco.entrega_esperada == "revisao" and marco.documento_base is not None:
        return str(marco.documento_base.id)
    if ultima is not None:
        return str(ultima.documento_id)
    return str(docs[0].id) if docs else NOVO_DOCUMENTO


@bp.route("/<int:marco_id>")
@login_required
def detalhe(orientacao_id: int, marco_id: int):
    """Página da tarefa, organizada pelo **próximo passo**: no topo, a única ação
    que cabe a quem está vendo (entregar, corrigir, conferir); abaixo, o
    histórico (devolução anterior, nota, entregas, reuniões)."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    # uma passada pelas entregas serve a tabela, o destino padrão e o
    # documento-alvo da devolução: cada `versao_atual` vai ao banco
    docs = marco.documentos_da_tarefa
    entregas = [(d, d.versao_atual) for d in docs]
    ultima = ultima_versao(entregas)

    entrega_form = EntregaTarefaForm()
    entrega_form.destino.choices = _escolhas_destino(docs)
    entrega_form.destino.data = _destino_padrao(marco, docs, ultima)
    entrega_form.titulo.data = marco.titulo
    if current_user.id == orientacao.orientando_id:
        del entrega_form.natureza  # o que a orientanda envia é sempre dela
    if not servico_cronograma.pode_sinalizar(marco, current_user):
        del entrega_form.sinalizar

    # o form de devolver aceita anexar o arquivo corrigido a um documento da
    # tarefa. Sem documentos, não há onde anexar: somem os campos de arquivo.
    devolver_form = DevolverForm()
    if docs:
        devolver_form.documento_id.choices = [(d.id, d.titulo) for d in docs]
        if ultima is not None:
            devolver_form.documento_id.data = ultima.documento_id
    else:
        del devolver_form.documento_id
        del devolver_form.arquivo
        del devolver_form.anexos
    return render_template(
        "cronogramas/detalhe.html",
        orientacao=orientacao,
        marco=marco,
        entregas=entregas,
        ultima=ultima,
        entrega_form=entrega_form,
        sinalizar_form=SinalizarForm(),
        confirmacao_form=ConfirmacaoForm(),
        devolver_form=devolver_form,
        materiais=servico_materiais.do_marco(marco),
    )


@bp.route("/<int:marco_id>/anexar", methods=["POST"])
@login_required
def anexar(orientacao_id: int, marco_id: int):
    """Envio pela tarefa: nova versão de um documento da tarefa ou documento
    novo ligado a ela — e, para a orientanda, a opção de já avisar o orientador
    (sinalizar) no mesmo ato. Disponível a qualquer participante do vínculo."""
    orientacao = orientacao_autorizada(orientacao_id)
    marco = _marco_da_orientacao(orientacao, marco_id)
    voltar = redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )
    if marco.status == "concluido":
        flash("A tarefa está concluída; não recebe novos envios.", "warning")
        return voltar
    docs = marco.documentos_da_tarefa
    form = EntregaTarefaForm()
    form.destino.choices = _escolhas_destino(docs)
    if form.destino.data is None and not docs:
        form.destino.data = NOVO_DOCUMENTO  # sem documentos, só há um destino
    eh_gestor = current_user.id != orientacao.orientando_id
    if not eh_gestor:
        del form.natureza
    sinaliza_possivel = servico_cronograma.pode_sinalizar(marco, current_user)
    if not sinaliza_possivel:
        del form.sinalizar
    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
        return voltar

    em_nome = eh_gestor and eh_entrega_da_orientanda(form.natureza.data)
    novo = form.destino.data == NOVO_DOCUMENTO
    if novo:
        documento = Documento(
            orientacao_id=orientacao.id,
            marco_id=marco.id,
            titulo=form.titulo.data.strip(),
            criado_por=current_user.id,
        )
        db.session.add(documento)
        db.session.flush()
    else:
        documento = next((d for d in docs if str(d.id) == form.destino.data), None)
        if documento is None:
            abort(404)
    try:
        versao = salvar_versao(
            documento, form.arquivo.data or None, current_user,
            form.comentario.data, em_nome_do_orientando=em_nome,
            anexos=form.anexos.data,
        )
    except UploadInvalido as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return voltar
    db.session.flush()
    dados = {"anexos": len(versao.anexos), "origem": "marco", "marco_id": marco.id,
             "natureza": versao.natureza}
    if novo:
        auditoria.registrar(
            "criacao_documento", "documento", documento.id,
            {"titulo": documento.titulo, "arquivo": versao.nome_original, **dados},
        )
    else:
        auditoria.registrar(
            "nova_versao_documento", "versao_documento", versao.id,
            {"documento_id": documento.id, "versao": versao.numero_versao, **dados},
        )
    sinalizou = sinaliza_possivel and form.sinalizar.data
    if sinalizou:
        servico_cronograma.sinalizar_conclusao(marco)
    db.session.commit()
    if novo:
        msg = f'Documento "{documento.titulo}" criado (versão 1).'
    else:
        msg = f'Versão {versao.numero_versao} de "{documento.titulo}" enviada.'
    if sinalizou:
        msg += " O orientador foi avisado para conferir."
    flash(msg, "success")
    return voltar


@bp.route("/<int:marco_id>/excluir", methods=["GET", "POST"])
@login_required
def excluir(orientacao_id: int, marco_id: int):
    """Exclui a tarefa individual criada por engano (duplicada). Só a limpa:
    com histórico — sinalizada, com documento, discutida em reunião — ela é
    preservada, como a tarefa em grupo e as contas. GET confirma; POST exclui."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    motivo = servico_cronograma.motivo_historico(marco)
    if motivo:
        auditoria.registrar(
            "exclusao_tarefa_recusada", "marco", marco.id, {"motivo": motivo}
        )
        db.session.commit()
        flash(
            f"A tarefa não pode ser excluída: {motivo}. Ela fica preservada; "
            "edite-a se precisar.",
            "danger",
        )
        return redirect(
            url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
        )
    form = ConfirmacaoForm()
    if form.validate_on_submit():
        titulo = marco.titulo
        auditoria.registrar(
            "exclusao_marco", "marco", marco.id,
            {"titulo": titulo, "data_prevista": str(marco.data_prevista),
             "grupo_id": marco.grupo_id},
        )
        servico_cronograma.excluir_marco(marco)
        db.session.commit()
        flash(f'Tarefa "{titulo}" excluída.', "success")
        return redirect(url_for("cronogramas.listar", orientacao_id=orientacao.id))
    return render_template(
        "cronogramas/excluir.html", orientacao=orientacao, marco=marco, form=form
    )


@bp.route("/<int:marco_id>/editar", methods=["GET", "POST"])
@login_required
def editar(orientacao_id: int, marco_id: int):
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = MarcoIndividualForm(obj=marco)
    _escolhas_texto_base(form, orientacao)
    if not form.is_submitted():
        form.entrega_esperada.data = marco.entrega_esperada or ""
        form.documento_base_id.data = marco.documento_base_id or 0
    if form.validate_on_submit():
        for campo in ("titulo", "tipo", "descricao", "data_prevista", "etapa"):
            setattr(marco, campo, getattr(form, campo).data)
        _aplicar_entrega_esperada(marco, form)
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
        servico_cronograma.sinalizar_conclusao(marco, form.nota.data)
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
    """A porta única de devolver: move o marco, grava a nota e, se veio o arquivo
    corrigido, anexa-o ao documento-alvo e carimba a versão como devolução — tudo
    num ato. RBAC do orientador principal/admin (o cronograma é dele)."""
    orientacao = orientacao_autorizada(orientacao_id)
    if not manda_no_cronograma(orientacao):
        abort(403)
    marco = _marco_da_orientacao(orientacao, marco_id)
    form = DevolverForm()
    docs = marco.documentos_da_tarefa
    form.documento_id.choices = [(d.id, d.titulo) for d in docs]
    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
        return redirect(
            url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
        )
    # a precondição é checada ANTES de gravar o arquivo, para não deixar versão
    # órfã quando não há entrega da orientanda a devolver
    if not servico_cronograma.pode_devolver(marco):
        flash(*servico_cronograma.recado_da_devolucao(marco))
        return redirect(
            url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
        )
    versao = None
    if form.anexos.data and not form.arquivo.data:
        flash(
            "Os anexos acompanham o arquivo corrigido: envie-o também. "
            "Nada foi devolvido.",
            "danger",
        )
        return redirect(
            url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
        )
    if form.arquivo.data:
        # arquivo sem documento-alvo (marco sem documentos) não pode ser anexado:
        # avisa em vez de descartar em silêncio, e devolve só com a nota
        if not form.documento_id.data:
            flash(
                "Os arquivos não foram anexados: a tarefa não tem documento para recebê-los. "
                "Anexe-os pela aba Documentos; a devolução seguiu só com a nota.",
                "warning",
            )
        else:
            documento = next((d for d in docs if d.id == form.documento_id.data), None)
            if documento is None:
                abort(404)
            try:
                # o arquivo é a versão corrigida; a nota vive na tarefa
                # (marco.nota_devolucao), não se duplica no comentário da versão
                versao = salvar_versao(
                    documento, form.arquivo.data, current_user,
                    anexos=form.anexos.data,
                )
            except UploadInvalido as exc:
                db.session.rollback()
                flash(str(exc), "danger")
                return redirect(
                    url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
                )
            db.session.flush()
    servico_cronograma.devolver_entrega(marco, form.nota.data, versao=versao)
    db.session.commit()
    flash("Entrega devolvida para revisão do orientando.", "success")
    return redirect(
        url_for("cronogramas.detalhe", orientacao_id=orientacao.id, marco_id=marco.id)
    )
