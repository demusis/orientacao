from datetime import datetime, timezone

from app.extensions import db


class LogAuditoria(db.Model):
    """Trilha append-only. A aplicação não expõe UPDATE/DELETE sobre esta tabela;
    toda escrita ocorre exclusivamente via services/auditoria.py."""

    __tablename__ = "log_auditoria"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    acao = db.Column(db.String(100), nullable=False)
    entidade = db.Column(db.String(50), nullable=False)
    entidade_id = db.Column(db.Integer, nullable=True)
    dados_json = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    usuario = db.relationship("Usuario")

    def __repr__(self) -> str:
        return f"<LogAuditoria {self.acao} {self.entidade}#{self.entidade_id}>"
