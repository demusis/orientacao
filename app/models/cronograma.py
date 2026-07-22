from datetime import date

from app.extensions import db

STATUS_MARCO = ("pendente", "em_andamento", "concluido")

# Os dois eixos de classificação do marco respondem a perguntas distintas e não
# compartilham rótulo algum — a sobreposição anterior (qualificação, publicação
# e defesa figuravam nas duas listas) permitia registrar a mesma informação em
# dois lugares, ou em nenhum.
#
# TIPO é o ato ou produto devido na data do marco. Só entra aqui o que o
# orientador aprecia, assina ou julga em banca: o campo não altera permissão,
# prazo nem documento exigido, de modo que uma categoria a mais custa atenção em
# toda abertura da caixa de seleção e rende apenas uma contagem agregada. O que
# fica de fora (apresentação em evento, proficiência em idioma) continua a ser
# registrável como "outro", com o título descrevendo o caso.
TIPOS_MARCO = (
    "outro",
    "projeto",
    "comite_etica",
    "qualificacao",
    "relatorio",
    "publicacao",
    "defesa",
)

TIPO_MARCO_LABEL = {
    "outro": "Outro",
    "projeto": "Projeto de pesquisa",
    "comite_etica": "Comitê de Ética",
    "qualificacao": "Qualificação",
    "relatorio": "Relatório (parcial, anual ou final)",
    "publicacao": "Publicação",
    "defesa": "Defesa",
}

# ETAPA é o período em que o marco se insere — dura semanas ou meses e abriga
# vários marcos. Substitui a antiga "ordem" numérica livre. Os códigos são
# inteiros espaçados de 10 — a ordenação do cronograma continua sendo feita no
# banco (sem expressão condicional) e novas etapas cabem entre as atuais sem
# renumerar as existentes. O código 0 é o padrão e agrupa o que ainda não foi
# classificado, aparecendo no topo do cronograma.
ETAPAS_MARCO = (0, 10, 20, 30, 40, 50, 60)

ETAPA_MARCO_LABEL = {
    0: "Não classificada",
    10: "Planejamento",
    20: "Revisão de literatura",
    30: "Coleta / Experimentos",
    40: "Análise de resultados",
    50: "Redação",
    60: "Encerramento",
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
    etapa = db.Column(db.Integer, nullable=False, default=0)
    conclusao_sinalizada = db.Column(db.Boolean, nullable=False, default=False)
    # nota opcional que o orientando escreve ao sinalizar a conclusão
    nota_conclusao = db.Column(db.Text, nullable=True)
    # UUID hex comum aos marcos criados por uma mesma tarefa em grupo
    grupo_id = db.Column(db.String(32), nullable=True, index=True)

    orientacao = db.relationship("Orientacao", back_populates="marcos")
    # entregas feitas para esta etapa (Documento.marco_id) e reuniões que a
    # discutiram (M:N ata_marco) — as ligações que tornam o marco um eixo
    documentos = db.relationship("Documento", back_populates="marco")
    atas = db.relationship(
        "Ata", secondary="ata_marco", order_by="Ata.data_reuniao", viewonly=True
    )

    @property
    def atrasado(self) -> bool:
        """Computado na leitura; não depende de scheduler (risco R7)."""
        return self.status != "concluido" and self.data_prevista < date.today()

    @property
    def tem_historico(self) -> bool:
        """Verdadeiro se o marco já acumulou registro que a exclusão apagaria:
        saiu do estado inicial, foi sinalizado, recebeu documento ou foi
        discutido em reunião. Marco 'limpo' pode ser excluído; com histórico,
        segue a filosofia do sistema — preservar, não apagar."""
        return (
            self.status != "pendente"
            or self.conclusao_sinalizada
            or bool(self.documentos)
            or bool(self.atas)
        )

    def __repr__(self) -> str:
        return f"<Marco {self.id} {self.titulo!r} {self.status}>"
