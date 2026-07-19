from datetime import datetime, timezone

from app.extensions import db

MODALIDADES = ("ic", "mestrado", "doutorado")
STATUS_ORIENTACAO = ("ativa", "concluida", "suspensa", "cancelada")

MODALIDADE_LABEL = {
    "ic": "Iniciação Científica",
    "mestrado": "Mestrado",
    "doutorado": "Doutorado",
}


class Orientacao(db.Model):
    __tablename__ = "orientacao"

    id = db.Column(db.Integer, primary_key=True)
    orientador_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    orientando_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    modalidade = db.Column(
        db.Enum(*MODALIDADES, name="modalidade_orientacao"), nullable=False
    )
    titulo_projeto = db.Column(db.String(255), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim_prevista = db.Column(db.Date, nullable=True)
    status = db.Column(
        db.Enum(*STATUS_ORIENTACAO, name="status_orientacao"),
        nullable=False,
        default="ativa",
    )
    criado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientador = db.relationship(
        "Usuario",
        foreign_keys=[orientador_id],
        back_populates="orientacoes_como_orientador",
    )
    orientando = db.relationship(
        "Usuario",
        foreign_keys=[orientando_id],
        back_populates="orientacoes_como_orientando",
    )
    marcos = db.relationship(
        "Marco", back_populates="orientacao", order_by="Marco.ordem", lazy="dynamic"
    )
    documentos = db.relationship("Documento", back_populates="orientacao", lazy="dynamic")
    atas = db.relationship(
        "Ata", secondary="ata_orientacao", back_populates="orientacoes", lazy="dynamic"
    )
    pareceres = db.relationship("Parecer", back_populates="orientacao", lazy="dynamic")

    def envolve(self, usuario) -> bool:
        return usuario.id in (self.orientador_id, self.orientando_id)

    def __repr__(self) -> str:
        return f"<Orientacao {self.id} {self.modalidade} {self.status}>"
