from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager

PAPEIS = ("admin", "orientador", "orientando")


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.Enum(*PAPEIS, name="papel_usuario"), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    criado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    # Registro do último login bem-sucedido. Serve à medição agregada de adesão
    # (contas ociosas, nunca acessadas); não registra o que a pessoa fez —
    # leituras permanecem fora da auditoria por decisão de 20/07/2026.
    ultimo_acesso = db.Column(db.DateTime, nullable=True)

    orientacoes_como_orientador = db.relationship(
        "Orientacao",
        foreign_keys="Orientacao.orientador_id",
        back_populates="orientador",
        lazy="dynamic",
    )
    orientacoes_como_orientando = db.relationship(
        "Orientacao",
        foreign_keys="Orientacao.orientando_id",
        back_populates="orientando",
        lazy="dynamic",
    )

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self) -> bool:
        return self.ativo

    def get_id(self) -> str:
        """Identidade da sessão: id mais um trecho do hash da senha.

        Trocada a senha, o trecho muda e as sessões abertas com o valor antigo
        deixam de casar em `load_user` — encerram-se. Sem isto, redefinir a senha
        por suspeita de acesso indevido deixaria viva a sessão do invasor, que é
        exatamente o cenário em que a redefinição precisa servir."""
        return f"{self.id}:{(self.senha_hash or '')[-16:]}"

    def __repr__(self) -> str:
        return f"<Usuario {self.email} ({self.papel})>"


@login_manager.user_loader
def load_user(identidade: str):
    # tolera o formato antigo (só o id) para não deslogar todos na implantação;
    # sessões existentes seguem válidas até expirar
    id_txt, _, marca = identidade.partition(":")
    usuario = db.session.get(Usuario, int(id_txt))
    if usuario is None:
        return None
    if marca and marca != (usuario.senha_hash or "")[-16:]:
        return None  # senha trocada desde que a sessão foi aberta
    return usuario
