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


def motivo_bloqueio_exclusao(usuario: Usuario) -> str | None:
    """Retorna o motivo que impede a exclusão física, ou None se a conta é limpa."""
    verificacoes = [
        (
            Orientacao.query.filter(
                (Orientacao.orientador_id == usuario.id)
                | (Orientacao.orientando_id == usuario.id)
            ),
            "participa de vínculo de orientação",
        ),
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


def excluir_usuario(usuario: Usuario, executor: Usuario) -> None:
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
    motivo = motivo_bloqueio_exclusao(usuario)
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
        {"email": usuario.email, "papel": usuario.papel},
    )
    db.session.delete(usuario)
