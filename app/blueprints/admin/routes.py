import json

from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user

from app.blueprints.admin import bp
from app.blueprints.admin.forms import (
    AjusteDatasForm,
    ConfiguracaoEmailForm,
    CoorientadorForm,
    EncerrarOrientacaoForm,
    ExcluirForm,
    ExpurgarBaseForm,
    FiltroAuditoriaForm,
    GerarBackupForm,
    OrientacaoForm,
    RestaurarBackupForm,
    RemoverForm,
    TesteEmailForm,
    UsuarioForm,
)
from app.extensions import db
from app.models import (
    ConfiguracaoEmail,
    LogAuditoria,
    Orientacao,
    OrientacaoOrientador,
    Usuario,
)
from app.services import auditoria, avisos, cripto
from app.services import email as email_service
from app.services import usuarios as usuarios_service
from app.services.rbac import role_required
from app.services.usuarios import GestaoUsuarioInvalida


@bp.route("/usuarios")
@role_required("admin")
def listar_usuarios():
    paginacao = Usuario.query.order_by(Usuario.nome).paginate(
        page=request.args.get("pagina", 1, type=int),
        per_page=current_app.config["ITENS_POR_PAGINA"],
        error_out=False,
    )
    return render_template(
        "admin/usuarios.html",
        usuarios=paginacao.items,
        paginacao=paginacao,
        excluir_form=ExcluirForm(),
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
                    telefone=form.telefone.data,
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
        usuario.telefone = form.telefone.data or None
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
    paginacao = Orientacao.query.order_by(Orientacao.criado_em.desc()).paginate(
        page=request.args.get("pagina", 1, type=int),
        per_page=current_app.config["ITENS_POR_PAGINA"],
        error_out=False,
    )
    return render_template(
        "admin/orientacoes.html",
        orientacoes=paginacao.items,
        paginacao=paginacao,
    )


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
    administrador; o orientador altera apenas o título. É o único caminho para o
    prazo do vínculo desde que o registro de eventos foi removido, daí exigir
    fundamentação: a trilha guardava as datas, mas não o motivo."""
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
                "fundamentacao": form.fundamentacao.data,
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


@bp.route("/email", methods=["GET", "POST"])
@role_required("admin")
def configurar_email():
    """Configuração do envio de e-mail. A senha de app é guardada cifrada e
    nunca devolvida à tela; ver `services/cripto.py` quanto ao que a cifragem
    protege e ao que ela não protege."""
    config = ConfiguracaoEmail.vigente()
    form = ConfiguracaoEmailForm(obj=config)
    if request.method == "GET":
        # campo de escrita apenas: chega em branco à tela. Zerar isto também no
        # POST descartaria a senha recém-digitada — e nenhuma senha jamais seria
        # gravada.
        form.senha.data = ""
    teste_form = TesteEmailForm(destinatario=current_user.email)

    if form.validate_on_submit():
        config.ativo = form.ativo.data
        config.servidor = form.servidor.data.strip()
        config.porta = form.porta.data
        config.usuario = form.usuario.data.strip()
        config.remetente_nome = form.remetente_nome.data.strip()
        if form.senha.data:
            config.senha_cifrada = cripto.cifrar(form.senha.data)
        config.registrar_alteracao(current_user.id)
        # a senha não entra nos dados auditados — a trilha registra a mudança,
        # não o segredo
        auditoria.registrar(
            "configuracao_email",
            "configuracao_email",
            config.id,
            {
                "servidor": config.servidor,
                "porta": config.porta,
                "usuario": config.usuario,
                "ativo": config.ativo,
                "senha_alterada": bool(form.senha.data),
            },
        )
        db.session.commit()
        flash("Configuração de e-mail salva.", "success")
        return redirect(url_for("admin.configurar_email"))

    db.session.commit()  # persiste a linha criada por vigente() na primeira visita
    pendentes = avisos.coletar()
    ultimo_envio = (
        LogAuditoria.query.filter_by(acao="envio_avisos")
        .order_by(LogAuditoria.timestamp.desc())
        .first()
    )
    return render_template(
        "admin/email.html",
        form=form,
        teste_form=teste_form,
        config=config,
        # a trilha já guarda o histórico dos envios; dispensa coluna própria
        ultimo_envio=ultimo_envio,
        resumo_ultimo=json.loads(ultimo_envio.dados_json) if ultimo_envio and ultimo_envio.dados_json else None,
        pendentes={
            "destinatarios": len(pendentes),
            "itens": sum(len(i) for s in pendentes.values() for i in s.values()),
        },
    )


@bp.route("/email/teste", methods=["POST"])
@role_required("admin")
def testar_email():
    form = TesteEmailForm()
    if form.validate_on_submit():
        erro = email_service.testar(form.destinatario.data.strip())
        if erro:
            flash(erro, "danger")
        else:
            flash(
                f"E-mail de teste enviado para {form.destinatario.data}. "
                "Confira a caixa de entrada e o spam.",
                "success",
            )
    else:
        flash("Informe um endereço válido para o teste.", "danger")
    return redirect(url_for("admin.configurar_email"))


@bp.route("/backup", methods=["GET"])
@role_required("admin")
def backup():
    from app.services.backup import ORDEM_TABELAS, _contagens

    return render_template(
        "admin/backup.html",
        contagens=_contagens(),
        tabelas=ORDEM_TABELAS,
        gerar_form=GerarBackupForm(),
        restaurar_form=RestaurarBackupForm(),
        expurgar_form=ExpurgarBaseForm(),
    )


@bp.route("/backup/gerar", methods=["POST"])
@role_required("admin")
def gerar_backup():
    from app.services import backup as servico

    form = GerarBackupForm()
    if not form.validate_on_submit():
        return redirect(url_for("admin.backup"))
    nome, conteudo = servico.gerar()
    auditoria.registrar("geracao_backup", "sistema", None, {"arquivo": nome})
    db.session.commit()
    return Response(
        conteudo,
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )


@bp.route("/backup/restaurar", methods=["POST"])
@role_required("admin")
def restaurar_backup():
    from app.services import backup as servico

    form = RestaurarBackupForm()
    if form.validate_on_submit():
        try:
            resumo = servico.restaurar(form.arquivo.data, current_user)
            # a sessão apontava para uma linha que deixou de existir; reautentica
            # com o registro vigente antes de auditar e seguir
            reingresso = Usuario.query.filter_by(
                email=resumo["email_executor"]
            ).one()
            login_user(reingresso)
            auditoria.registrar("restauracao_backup", "sistema", None, resumo)
            db.session.commit()
            aviso = (
                " Sua conta foi preservada por não constar do backup."
                if resumo["executor_preservado"]
                else ""
            )
            flash(
                f"Backup restaurado: {sum(resumo['contagens'].values())} registro(s) e "
                f"{resumo['arquivos']} arquivo(s).{aviso}",
                "success",
            )
        except servico.BackupInvalido as exc:
            db.session.rollback()
            flash(f"Restauração recusada: {exc}", "danger")
        return redirect(url_for("admin.backup"))
    for erros in form.errors.values():
        for erro in erros:
            flash(erro, "danger")
    return redirect(url_for("admin.backup"))


@bp.route("/backup/expurgar", methods=["POST"])
@role_required("admin")
def expurgar_base():
    from app.services import backup as servico

    form = ExpurgarBaseForm()
    if form.validate_on_submit():
        removidos = servico.expurgar(current_user)
        db.session.commit()
        flash(
            f"Base apagada: {sum(removidos.values())} registro(s) removido(s). "
            "Apenas a sua conta foi preservada.",
            "success",
        )
        return redirect(url_for("admin.backup"))
    for erros in form.errors.values():
        for erro in erros:
            flash(erro, "danger")
    return redirect(url_for("admin.backup"))


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
