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

# Etapa do projeto: substitui a antiga "ordem" numérica livre. Os códigos são
# inteiros espaçados de 10 — a ordenação do cronograma continua sendo feita no
# banco (sem expressão condicional) e novas etapas cabem entre as atuais sem
# renumerar as existentes. O código 0 é o padrão e agrupa o que ainda não foi
# classificado, aparecendo no topo do cronograma.
ETAPAS_MARCO = (0, 10, 20, 30, 40, 50, 60, 70, 80)

ETAPA_MARCO_LABEL = {
    0: "Não classificada",
    10: "Planejamento",
    20: "Revisão de literatura",
    30: "Qualificação",
    40: "Coleta / Experimentos",
    50: "Análise de resultados",
    60: "Redação",
    70: "Publicação",
    80: "Defesa",
}

# Etapas que correspondem a um ato formal já previsto em TIPOS_MARCO: quando o
# tipo não foi especificado, deriva-se dele para não exigir a mesma informação
# duas vezes.
TIPO_IMPLICADO_PELA_ETAPA = {30: "qualificacao", 70: "publicacao", 80: "defesa"}


def tipo_do_marco(tipo_informado: str, etapa: int) -> str:
    """Completa o tipo a partir da etapa quando ele foi deixado em 'outro'
    (valor padrão, que significa 'não especificado'). Tipo escolhido de forma
    explícita nunca é sobrescrito."""
    if tipo_informado != "outro":
        return tipo_informado
    return TIPO_IMPLICADO_PELA_ETAPA.get(etapa, "outro")


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
    etapa = db.Column(db.Integer, nullable=False, default=0)
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
