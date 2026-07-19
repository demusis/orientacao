from datetime import datetime, timezone

from app.extensions import db

STATUS_ATA = ("rascunho", "finalizada")
TIPOS_PARECER = ("andamento", "documento", "marco")
RESULTADOS_PARECER = ("aprovado", "aprovado_com_ressalvas", "reprovado")

RESULTADO_LABEL = {
    "aprovado": "Aprovado",
    "aprovado_com_ressalvas": "Aprovado com ressalvas",
    "reprovado": "Reprovado",
}


class Ata(db.Model):
    __tablename__ = "ata"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
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

    orientacao = db.relationship("Orientacao", back_populates="atas")
    redator = db.relationship("Usuario", foreign_keys=[redigida_por])

    @property
    def imutavel(self) -> bool:
        return self.status == "finalizada"

    def __repr__(self) -> str:
        return f"<Ata {self.id} {self.status}>"


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
