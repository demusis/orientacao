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
        "Ata", secondary="ata_orientacao", viewonly=True, lazy="dynamic"
    )
    pareceres = db.relationship("Parecer", back_populates="orientacao", lazy="dynamic")

    eventos = db.relationship(
        "EventoVinculo",
        back_populates="orientacao",
        order_by="EventoVinculo.registrado_em",
    )
    equipe = db.relationship(
        "OrientacaoOrientador",
        back_populates="orientacao",
        cascade="all, delete-orphan",
    )

    @property
    def coorientadores(self):
        return [a.usuario for a in self.equipe if a.funcao == "coorientador"]

    def orienta(self, usuario) -> bool:
        """Usuário integra a equipe de orientação (principal ou coorientador)."""
        if usuario.id == self.orientador_id:
            return True
        return any(a.usuario_id == usuario.id for a in self.equipe)

    def envolve(self, usuario) -> bool:
        return usuario.id == self.orientando_id or self.orienta(usuario)

    def __repr__(self) -> str:
        return f"<Orientacao {self.id} {self.modalidade} {self.status}>"


FUNCOES_ORIENTADOR = ("principal", "coorientador")


class OrientacaoOrientador(db.Model):
    """Coorientadores do vínculo. O orientador principal tem fonte única em
    Orientacao.orientador_id — esta tabela registra APENAS coorientadores
    (funcao='coorientador'); linhas 'principal' foram removidas na migração
    f2b6d81c4a55 para eliminar a dupla representação."""

    __tablename__ = "orientacao_orientador"

    orientacao_id = db.Column(
        db.Integer, db.ForeignKey("orientacao.id"), primary_key=True
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), primary_key=True)
    funcao = db.Column(
        db.Enum(*FUNCOES_ORIENTADOR, name="funcao_orientador"),
        nullable=False,
        default="coorientador",
    )
    designado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientacao = db.relationship("Orientacao", back_populates="equipe")
    usuario = db.relationship("Usuario")

    def __repr__(self) -> str:
        return f"<OrientacaoOrientador o={self.orientacao_id} u={self.usuario_id} {self.funcao}>"


TIPOS_EVENTO = ("prorrogacao", "trancamento", "destrancamento", "mudanca_titulo")

TIPO_EVENTO_LABEL = {
    "prorrogacao": "Prorrogação de prazo",
    "trancamento": "Trancamento",
    "destrancamento": "Destrancamento",
    "mudanca_titulo": "Mudança de título",
}


class EventoVinculo(db.Model):
    """Ato formal sobre o vínculo (prorrogação, trancamento etc.), com
    fundamentação obrigatória e carimbo de data/hora. Preserva o histórico dos
    valores alterados."""

    __tablename__ = "evento_vinculo"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
    tipo = db.Column(db.Enum(*TIPOS_EVENTO, name="tipo_evento"), nullable=False)
    fundamentacao = db.Column(db.Text, nullable=False)
    data_anterior = db.Column(db.Date, nullable=True)
    data_nova = db.Column(db.Date, nullable=True)
    texto_anterior = db.Column(db.String(255), nullable=True)
    texto_novo = db.Column(db.String(255), nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    registrado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    orientacao = db.relationship("Orientacao", back_populates="eventos")
    autor = db.relationship("Usuario", foreign_keys=[registrado_por])

    def __repr__(self) -> str:
        return f"<EventoVinculo {self.id} {self.tipo} orientacao={self.orientacao_id}>"
