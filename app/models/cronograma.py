from datetime import date

from app.extensions import db

STATUS_MARCO = ("pendente", "em_andamento", "concluido")
TIPOS_MARCO = (
    "outro",
    "qualificacao",
    "defesa",
    "relatorio_anual",
    "proficiencia",
    "publicacao",
)

TIPO_MARCO_LABEL = {
    "outro": "Outro",
    "qualificacao": "Qualificação",
    "defesa": "Defesa",
    "relatorio_anual": "Relatório anual",
    "proficiencia": "Proficiência",
    "publicacao": "Publicação",
}


class Marco(db.Model):
    __tablename__ = "marco"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
    titulo = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    data_prevista = db.Column(db.Date, nullable=False)
    data_conclusao = db.Column(db.Date, nullable=True)
    status = db.Column(
        db.Enum(*STATUS_MARCO, name="status_marco"), nullable=False, default="pendente"
    )
    tipo = db.Column(
        db.Enum(*TIPOS_MARCO, name="tipo_marco"), nullable=False, default="outro"
    )
    ordem = db.Column(db.Integer, nullable=False, default=0)
    conclusao_sinalizada = db.Column(db.Boolean, nullable=False, default=False)
    # UUID hex comum aos marcos criados por uma mesma tarefa em grupo
    grupo_id = db.Column(db.String(32), nullable=True, index=True)

    orientacao = db.relationship("Orientacao", back_populates="marcos")

    @property
    def atrasado(self) -> bool:
        """Computado na leitura; não depende de scheduler (risco R7)."""
        return self.status != "concluido" and self.data_prevista < date.today()

    def __repr__(self) -> str:
        return f"<Marco {self.id} {self.titulo!r} {self.status}>"
