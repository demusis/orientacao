from datetime import datetime, timezone

from app.extensions import db

STATUS_ATA = ("rascunho", "finalizada")
TIPOS_ATA = ("individual", "grupo")
TIPOS_PARECER = ("andamento", "documento", "marco")
RESULTADOS_PARECER = ("aprovado", "aprovado_com_ressalvas", "reprovado")

RESULTADO_LABEL = {
    "aprovado": "Aprovado",
    "aprovado_com_ressalvas": "Aprovado com ressalvas",
    "reprovado": "Reprovado",
}

ata_orientacao = db.Table(
    "ata_orientacao",
    db.Column("ata_id", db.Integer, db.ForeignKey("ata.id"), primary_key=True),
    db.Column("orientacao_id", db.Integer, db.ForeignKey("orientacao.id"), primary_key=True),
)


class Ata(db.Model):
    """Registro de reunião de orientação. Reunião individual associa-se a um
    vínculo; reunião em grupo, a vários vínculos do mesmo orientador (M:N)."""

    __tablename__ = "ata"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(
        db.Enum(*TIPOS_ATA, name="tipo_ata"), nullable=False, default="individual"
    )
    orientador_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    data_reuniao = db.Column(db.Date, nullable=False)
    pauta = db.Column(db.Text, nullable=False)
    deliberacoes = db.Column(db.Text, nullable=False)
    redigida_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    status = db.Column(
        db.Enum(*STATUS_ATA, name="status_ata"), nullable=False, default="rascunho"
    )
    finalizada_em = db.Column(db.DateTime, nullable=True)
    criada_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientacoes = db.relationship(
        "Orientacao", secondary=ata_orientacao, back_populates="atas"
    )
    orientador = db.relationship("Usuario", foreign_keys=[orientador_id])
    redator = db.relationship("Usuario", foreign_keys=[redigida_por])

    @property
    def imutavel(self) -> bool:
        return self.status == "finalizada"

    def __repr__(self) -> str:
        return f"<Ata {self.id} {self.tipo} {self.status}>"


class Parecer(db.Model):
    __tablename__ = "parecer"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
    versao_documento_id = db.Column(
        db.Integer, db.ForeignKey("versao_documento.id"), nullable=True
    )
    tipo = db.Column(db.Enum(*TIPOS_PARECER, name="tipo_parecer"), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    resultado = db.Column(
        db.Enum(*RESULTADOS_PARECER, name="resultado_parecer"), nullable=False
    )
    emitido_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    emitido_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientacao = db.relationship("Orientacao", back_populates="pareceres")
    versao_documento = db.relationship("VersaoDocumento")
    emissor = db.relationship("Usuario", foreign_keys=[emitido_por])

    def __repr__(self) -> str:
        return f"<Parecer {self.id} {self.tipo} {self.resultado}>"
