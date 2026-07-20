"""Gestão de contas: criação e exclusão com salvaguardas de integridade.

Exclusão física é admitida apenas para contas sem qualquer vestígio no sistema
(vínculos, conteúdo ou ações auditadas); do contrário, a via correta é a
desativação, que preserva o histórico."""
from app.extensions import db
from app.models import (
    Ata,
    Documento,
    LogAuditoria,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Reagendamento,
    Usuario,
    VersaoDocumento,
)
from app.models.ata import AtaParticipacao
from app.services import auditoria


class GestaoUsuarioInvalida(Exception):
    pass


def vinculo_sem_registros(orientacao: Orientacao) -> bool:
    """Vínculo que nada acumulou: nenhum marco, documento, ata, parecer, evento
    ou coorientador. Só um vínculo assim pode ser descartado com a conta."""
    return not (
        orientacao.marcos.first()
        or orientacao.documentos.first()
        or orientacao.atas.first()
        or orientacao.pareceres.first()
        or orientacao.eventos
        or orientacao.equipe
    )


def vinculos_descartaveis(usuario: Usuario) -> list[int]:
    """Vínculos em que a conta figura como orientando e que ainda não
    acumularam registro. Como o vínculo nasce junto com a conta (o orientador
    que cria o orientando torna-se seu orientador), exigir ausência de vínculo
    para excluir tornaria a exclusão impossível; o que se exige é ausência de
    histórico."""
    return [
        o.id
        for o in Orientacao.query.filter_by(orientando_id=usuario.id)
        if vinculo_sem_registros(o)
    ]


def motivo_bloqueio_exclusao(
    usuario: Usuario, descartaveis: list[int] | None = None
) -> str | None:
    """Retorna o motivo que impede a exclusão física, ou None se a conta é
    limpa. `descartaveis` lista vínculos vazios que serão removidos junto e
    que, portanto, não contam como vestígio."""
    descartaveis = descartaveis or []
    consulta_vinculos = Orientacao.query.filter(
        (Orientacao.orientador_id == usuario.id)
        | (Orientacao.orientando_id == usuario.id)
    )
    if descartaveis:
        consulta_vinculos = consulta_vinculos.filter(
            Orientacao.id.notin_(descartaveis)
        )
    verificacoes = [
        (consulta_vinculos, "participa de vínculo de orientação"),
        (LogAuditoria.query.filter_by(usuario_id=usuario.id), "possui ações auditadas"),
        (Documento.query.filter_by(criado_por=usuario.id), "criou documentos"),
        (VersaoDocumento.query.filter_by(enviado_por=usuario.id), "enviou versões"),
        (
            Ata.query.filter(
                (Ata.redigida_por == usuario.id) | (Ata.orientador_id == usuario.id)
            ),
            "figura em atas",
        ),
        (Parecer.query.filter_by(emitido_por=usuario.id), "emitiu pareceres"),
        (
            AtaParticipacao.query.filter_by(presenca_registrada_por=usuario.id),
            "registrou presenças",
        ),
        (
            Reagendamento.query.filter_by(registrado_por=usuario.id),
            "registrou reagendamentos",
        ),
        (
            OrientacaoOrientador.query.filter_by(usuario_id=usuario.id),
            "integra equipe de orientação (coorientação)",
        ),
        (Usuario.query.filter_by(criado_por=usuario.id), "criou outras contas"),
    ]
    for consulta, motivo in verificacoes:
        if db.session.query(consulta.exists()).scalar():
            return motivo
    return None


def criar_usuario(*, nome, email, papel, senha, autor, ativo=True) -> Usuario:
    if Usuario.query.filter_by(email=email).first():
        raise GestaoUsuarioInvalida("E-mail já cadastrado.")
    usuario = Usuario(
        nome=nome, email=email, papel=papel, ativo=ativo, criado_por=autor.id
    )
    usuario.set_senha(senha)
    db.session.add(usuario)
    db.session.flush()
    auditoria.registrar(
        "criacao_usuario", "usuario", usuario.id, {"email": email, "papel": papel}
    )
    return usuario


def criar_orientando_com_vinculo(
    *,
    nome,
    email,
    senha,
    orientador: Usuario,
    modalidade,
    titulo_projeto,
    data_inicio,
    data_fim_prevista=None,
) -> Orientacao:
    """Cria a conta do orientando e, no mesmo ato, o vínculo de orientação com
    quem a criou. Dispensa a intermediação do administrador."""
    usuario = criar_usuario(
        nome=nome,
        email=email,
        papel="orientando",
        senha=senha,
        autor=orientador,
    )
    orientacao = Orientacao(
        orientador_id=orientador.id,
        orientando_id=usuario.id,
        modalidade=modalidade,
        titulo_projeto=titulo_projeto,
        data_inicio=data_inicio,
        data_fim_prevista=data_fim_prevista,
    )
    db.session.add(orientacao)
    db.session.flush()
    auditoria.registrar(
        "criacao_orientacao",
        "orientacao",
        orientacao.id,
        {
            "orientador_id": orientador.id,
            "orientando_id": usuario.id,
            "modalidade": modalidade,
            "origem": "criacao_de_orientando",
        },
    )
    return orientacao


def excluir_usuario(
    usuario: Usuario, executor: Usuario, descartaveis: list[int] | None = None
) -> None:
    if usuario.id == executor.id:
        auditoria.registrar("autoexclusao_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida("Não é possível excluir a própria conta.")
    if (
        usuario.papel == "admin"
        and usuario.ativo
        and Usuario.query.filter_by(papel="admin", ativo=True).count() <= 1
    ):
        auditoria.registrar("exclusao_ultimo_admin_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(
            "O sistema deve manter ao menos um administrador ativo."
        )
    # revalida no serviço: só vínculos efetivamente vazios podem ser descartados
    descartaveis = [
        oid
        for oid in (descartaveis or [])
        if (o := db.session.get(Orientacao, oid)) is not None
        and o.orientando_id == usuario.id
        and vinculo_sem_registros(o)
    ]
    motivo = motivo_bloqueio_exclusao(usuario, descartaveis)
    if motivo:
        auditoria.registrar(
            "exclusao_recusada", "usuario", usuario.id, {"motivo": motivo}
        )
        raise GestaoUsuarioInvalida(
            f"Exclusão recusada: a conta {motivo}. Utilize a desativação, "
            "que preserva o histórico."
        )
    auditoria.registrar(
        "exclusao_usuario",
        "usuario",
        usuario.id,
        {
            "email": usuario.email,
            "papel": usuario.papel,
            "vinculos_removidos": descartaveis,
        },
    )
    for oid in descartaveis:
        db.session.delete(db.session.get(Orientacao, oid))
    db.session.delete(usuario)
