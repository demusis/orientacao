import json
from datetime import UTC, datetime

from app.extensions import db

FORMATOS_CONTEUDO = ("texto", "markdown")


def _formato_congelado(conteudo_congelado: str | None, formato_gravado: str) -> str:
    """Formato dos campos longos.

    Congelado o registro, manda o snapshot: é ele que o PDF assinado imprime, e
    a ausência da chave indica documento anterior à adoção do markdown.

    Ainda em rascunho, manda a coluna `formato`, gravada na criação. A versão
    anterior devolvia "markdown" para todo rascunho, o que reinterpretava como
    marcação os rascunhos redigidos ANTES da adoção — uma pauta com
    "# de participantes: 4" perdia o "#", e a perda virava permanente ao
    finalizar. A coluna é o que distingue um rascunho antigo de um novo, coisa
    que nenhuma heurística sobre o conteúdo faria com segurança."""
    if not conteudo_congelado:
        return formato_gravado or "texto"
    try:
        return json.loads(conteudo_congelado).get("formato", "texto")
    except ValueError:
        return "texto"


# "cancelada" é reunião que não vai acontecer: sai da agenda, dos lembretes e
# das pendências sem alterar consulta alguma, pois todas filtram por "rascunho".
STATUS_ATA = ("rascunho", "finalizada", "cancelada")
TIPOS_ATA = ("individual", "grupo")
TIPOS_PARECER = ("andamento", "documento", "marco")
RESULTADOS_PARECER = ("aprovado", "aprovado_com_ressalvas", "reprovado")

RESULTADO_LABEL = {
    "aprovado": "Aprovado",
    "aprovado_com_ressalvas": "Aprovado com ressalvas",
    "reprovado": "Reprovado",
}

PRESENCAS = ("pendente", "presente", "ausente")


class AtaParticipacao(db.Model):
    """Associação ata↔vínculo com registro de presença, assinalada pela equipe
    de orientação. As colunas de justificativa de ausência foram expurgadas do
    esquema em 19/07/2026 (LGPD: potencial dado sensível)."""

    __tablename__ = "ata_orientacao"

    ata_id = db.Column(db.Integer, db.ForeignKey("ata.id"), primary_key=True)
    orientacao_id = db.Column(
        db.Integer, db.ForeignKey("orientacao.id"), primary_key=True
    )
    presenca = db.Column(
        db.Enum(*PRESENCAS, name="presenca_ata"), nullable=False, default="pendente"
    )
    presenca_registrada_em = db.Column(db.DateTime, nullable=True)
    presenca_registrada_por = db.Column(
        db.Integer, db.ForeignKey("usuario.id"), nullable=True
    )

    ata = db.relationship("Ata", back_populates="participacoes")
    orientacao = db.relationship("Orientacao")
    registrador = db.relationship("Usuario", foreign_keys=[presenca_registrada_por])

    def __repr__(self) -> str:
        return f"<AtaParticipacao ata={self.ata_id} orientacao={self.orientacao_id} {self.presenca}>"


# Marcos discutidos na reunião. Associação pura (sem atributos), daí uma Table
# em vez de um modelo. Editável só enquanto a ata é rascunho; finalizada, congela
# junto com o resto do registro imutável (imposto na rota, não no esquema).
ata_marco = db.Table(
    "ata_marco",
    db.Column("ata_id", db.Integer, db.ForeignKey("ata.id"), primary_key=True),
    db.Column("marco_id", db.Integer, db.ForeignKey("marco.id"), primary_key=True),
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
    hora_reuniao = db.Column(db.Time, nullable=True)
    pauta = db.Column(db.Text, nullable=False)
    deliberacoes = db.Column(db.Text, nullable=False)
    redigida_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    status = db.Column(
        db.Enum(*STATUS_ATA, name="status_ata"), nullable=False, default="rascunho"
    )
    finalizada_em = db.Column(db.DateTime, nullable=True)
    # cancelamento: a reunião marcada que não vai ocorrer. Guardado na própria
    # linha, e não só na auditoria, porque a tela precisa exibir o motivo sem
    # reconstituí-lo a partir do log.
    cancelada_em = db.Column(db.DateTime, nullable=True)
    cancelada_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    motivo_cancelamento = db.Column(db.Text, nullable=True)
    # JSON canônico do conteúdo impresso, congelado na finalização; fonte única
    # do PDF e do hash de integridade, estável a alterações externas posteriores
    # (título do projeto, nomes)
    conteudo_congelado = db.Column(db.Text, nullable=True)
    # Formato dos campos longos na redação. Registro criado antes da adoção do
    # markdown fica em "texto" pela migração de backfill, e assim permanece,
    # ainda que só venha a ser finalizado depois.
    formato = db.Column(
        db.Enum(*FORMATOS_CONTEUDO, name="formato_conteudo"),
        nullable=False,
        default="markdown",
    )
    criada_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    participacoes = db.relationship(
        "AtaParticipacao", back_populates="ata", cascade="all, delete-orphan"
    )
    orientacoes = db.relationship(
        "Orientacao", secondary="ata_orientacao", viewonly=True
    )
    marcos = db.relationship("Marco", secondary=ata_marco, order_by="Marco.data_prevista")
    reagendamentos = db.relationship(
        "Reagendamento", back_populates="ata", order_by="Reagendamento.registrado_em"
    )
    orientador = db.relationship("Usuario", foreign_keys=[orientador_id])
    redator = db.relationship("Usuario", foreign_keys=[redigida_por])
    cancelador = db.relationship("Usuario", foreign_keys=[cancelada_por])

    @property
    def imutavel(self) -> bool:
        """Registro fechado. Abrange a cancelada: reunião que não vai ocorrer
        não recebe presença, não se reagenda e não tem ata a redigir."""
        return self.status in ("finalizada", "cancelada")

    @property
    def agendada(self) -> bool:
        """Reunião marcada e ainda por acontecer."""
        return self.status == "rascunho" and not self.realizada

    @property
    def realizada(self) -> bool:
        """A data da reunião já passou.

        **Compara apenas a data, e de propósito.** `hora_reuniao` é hora de
        parede digitada pelo orientador, no fuso dele; o servidor roda em UTC e
        o sistema não guarda o fuso de ninguém. Confrontar as duas grandezas
        daria a reunião de hoje às 16:00 como realizada às 13:00 de Brasília,
        três horas antes de começar, e a tela anunciaria "a data já passou"
        para quem ainda vai à reunião.

        O preço é o oposto, e é o erro que se prefere: a reunião de hoje pela
        manhã só migra para "aguardando ata" na virada do dia. Nunca se declara
        passado o que ainda está por vir. Declarar o fuso da instituição em
        configuração resolveria de vez, e é o caminho quando houver usuários
        fora de um mesmo fuso."""
        if self.status != "rascunho":
            return False
        from app.services.tempo import agora

        return self.data_reuniao < agora().date()

    @property
    def ata_redigida(self) -> bool:
        """Deliberações preenchidas. Reunião agendada nasce com elas em branco:
        deliberação é o que se decidiu, e não existe antes do encontro."""
        return bool((self.deliberacoes or "").strip())

    @property
    def tem_historico(self) -> bool:
        """Verdadeiro se a reunião já acumulou registro que a exclusão apagaria.
        Espelha `Marco.tem_historico`: o que está limpo pode ser apagado; o que
        já produziu registro é preservado, e o caminho passa a ser cancelar."""
        return (
            self.ata_redigida
            or bool(self.reagendamentos)
            or bool(self.marcos)
            or any(p.presenca != "pendente" for p in self.participacoes)
        )

    @property
    def formato_conteudo(self) -> str:
        return _formato_congelado(self.conteudo_congelado, self.formato)

    def participacao_de(self, orientacao_id: int):
        return next(
            (p for p in self.participacoes if p.orientacao_id == orientacao_id), None
        )

    def __repr__(self) -> str:
        return f"<Ata {self.id} {self.tipo} {self.status}>"


class Reagendamento(db.Model):
    """Histórico de reagendamentos de uma reunião (ata em rascunho)."""

    __tablename__ = "reagendamento"

    id = db.Column(db.Integer, primary_key=True)
    ata_id = db.Column(db.Integer, db.ForeignKey("ata.id"), nullable=False)
    data_anterior = db.Column(db.Date, nullable=False)
    hora_anterior = db.Column(db.Time, nullable=True)
    data_nova = db.Column(db.Date, nullable=False)
    hora_nova = db.Column(db.Time, nullable=True)
    motivo = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    registrado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    ata = db.relationship("Ata", back_populates="reagendamentos")
    autor = db.relationship("Usuario", foreign_keys=[registrado_por])

    def __repr__(self) -> str:
        return f"<Reagendamento ata={self.ata_id} {self.data_anterior}→{self.data_nova}>"


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
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    # congelado na emissão (o parecer é imutável desde a criação)
    conteudo_congelado = db.Column(db.Text, nullable=True)
    # Formato dos campos longos na redação. Registro criado antes da adoção do
    # markdown fica em "texto" pela migração de backfill, e assim permanece,
    # ainda que só venha a ser finalizado depois.
    formato = db.Column(
        db.Enum(*FORMATOS_CONTEUDO, name="formato_conteudo"),
        nullable=False,
        default="markdown",
    )

    orientacao = db.relationship("Orientacao", back_populates="pareceres")
    versao_documento = db.relationship("VersaoDocumento")
    emissor = db.relationship("Usuario", foreign_keys=[emitido_por])

    @property
    def formato_conteudo(self) -> str:
        return _formato_congelado(self.conteudo_congelado, self.formato)

    def __repr__(self) -> str:
        return f"<Parecer {self.id} {self.tipo} {self.resultado}>"
