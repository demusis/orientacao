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

    def __repr__(self) -> str:
        return f"<Usuario {self.email} ({self.papel})>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(Usuario, int(user_id))
