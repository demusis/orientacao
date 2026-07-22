from datetime import datetime, timezone

from app.extensions import db


class Documento(db.Model):
    __tablename__ = "documento"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
    marco_id = db.Column(db.Integer, db.ForeignKey("marco.id"), nullable=True)
    titulo = db.Column(db.String(255), nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    criado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientacao = db.relationship("Orientacao", back_populates="documentos")
    marco = db.relationship("Marco", back_populates="documentos")
    autor = db.relationship("Usuario", foreign_keys=[criado_por])
    versoes = db.relationship(
        "VersaoDocumento",
        back_populates="documento",
        order_by="VersaoDocumento.numero_versao.desc()",
        lazy="dynamic",
    )

    @property
    def versao_atual(self):
        return self.versoes.first()

    def __repr__(self) -> str:
        return f"<Documento {self.id} {self.titulo!r}>"


class VersaoDocumento(db.Model):
    __tablename__ = "versao_documento"
    __table_args__ = (
        db.UniqueConstraint("documento_id", "numero_versao", name="uq_documento_versao"),
    )

    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey("documento.id"), nullable=False)
    numero_versao = db.Column(db.Integer, nullable=False)
    nome_original = db.Column(db.String(255), nullable=False)
    nome_fisico = db.Column(db.String(64), unique=True, nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    enviado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    enviado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    comentario = db.Column(db.Text, nullable=True)

    documento = db.relationship("Documento", back_populates="versoes")
    remetente = db.relationship("Usuario", foreign_keys=[enviado_por])

    def __repr__(self) -> str:
        return f"<VersaoDocumento doc={self.documento_id} v{self.numero_versao}>"


class ModeloDocumento(db.Model):
    """Arquivo-modelo, ponto de partida para os documentos. Acervo global gerido
    pelo administrador; não pertence a vínculo algum. Espelha as colunas de
    armazenamento de VersaoDocumento e mora na mesma pasta de uploads."""

    __tablename__ = "modelo_documento"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    nome_original = db.Column(db.String(255), nullable=False)
    nome_fisico = db.Column(db.String(64), unique=True, nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    enviado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    criado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    autor = db.relationship("Usuario", foreign_keys=[enviado_por])

    def __repr__(self) -> str:
        return f"<ModeloDocumento {self.id} {self.titulo!r}>"
