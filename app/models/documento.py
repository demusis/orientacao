from datetime import UTC, datetime

from app.extensions import db


class Documento(db.Model):
    __tablename__ = "documento"

    id = db.Column(db.Integer, primary_key=True)
    orientacao_id = db.Column(db.Integer, db.ForeignKey("orientacao.id"), nullable=False)
    marco_id = db.Column(db.Integer, db.ForeignKey("marco.id"), nullable=True)
    titulo = db.Column(db.String(255), nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    criado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
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
    # colunas de arquivo opcionais: uma versão pode ser só comentário (retorno
    # todo textual), sem arquivo anexado. nome_fisico segue unique — SQLite
    # admite múltiplos NULL sob unique.
    nome_original = db.Column(db.String(255), nullable=True)
    nome_fisico = db.Column(db.String(64), unique=True, nullable=True)
    tamanho_bytes = db.Column(db.Integer, nullable=True)
    mimetype = db.Column(db.String(100), nullable=True)
    enviado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    enviado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    comentario = db.Column(db.Text, nullable=True)
    # Versão enviada pelo orientador como devolução com correções (não é entrega
    # da orientanda a avaliar): fica fora de "aguardando parecer" e devolve a
    # tarefa. A distinção é por intenção, não por quem enviou — no fluxo misto,
    # o orientador tanto registra a entrega da aluna quanto devolve correções.
    eh_devolucao = db.Column(db.Boolean, nullable=False, default=False)
    # Versão que o orientador sobe EM NOME da orientanda (arquivo dela, recebido
    # por outro canal). Conta como entrega dela: pede parecer, como se ela mesma
    # tivesse enviado. Sem isto, o upload do orientador nunca entraria na lista.
    em_nome_do_orientando = db.Column(db.Boolean, nullable=False, default=False)

    documento = db.relationship("Documento", back_populates="versoes")
    remetente = db.relationship("Usuario", foreign_keys=[enviado_por])
    # arquivos além do principal (planilha, figuras, carta...). O principal
    # segue nas colunas acima — é o texto que o parecer avalia —, e por isso
    # tudo que já dependia de `nome_fisico` continua valendo sem mudança.
    anexos = db.relationship(
        "AnexoVersao",
        back_populates="versao",
        order_by="AnexoVersao.id",
        cascade="all, delete-orphan",
    )

    @property
    def tem_arquivo(self) -> bool:
        """A versão carrega um arquivo? Falso quando é só comentário. Governa o
        link de baixar, a coluna de arquivo e a elegibilidade a parecer."""
        return bool(self.nome_fisico)

    @property
    def enviada_pela_orientanda(self) -> bool:
        """A própria orientanda enviou esta versão? Então é entrega dela, sem
        pergunta: "de quem é" só faz sentido para o upload do orientador.

        Lida também antes do flush (auditoria logo após `salvar_versao`),
        quando só `documento_id` está preenchido: busca o documento pela chave."""
        documento = self.documento
        if documento is None and self.documento_id is not None:
            documento = db.session.get(Documento, self.documento_id)
        return (
            documento is not None
            and self.enviado_por == documento.orientacao.orientando_id
        )

    @property
    def natureza(self) -> str:
        """O que a versão é, em uma palavra: "devolucao" (correções do
        orientador), "entrega" (da orientanda — enviada por ela ou registrada em
        nome dela) ou "registro" (qualquer outro upload do orientador). É o
        vocabulário do formulário de envio e das etiquetas. Olhar só
        `em_nome_do_orientando` deixava a entrega autêntica dela como
        "registro", sem a etiqueta que a substituta recebia."""
        if self.eh_devolucao:
            return "devolucao"
        if self.em_nome_do_orientando or self.enviada_pela_orientanda:
            return "entrega"
        return "registro"

    @property
    def quantidade_arquivos(self) -> int:
        return (1 if self.tem_arquivo else 0) + len(self.anexos)

    def __repr__(self) -> str:
        return f"<VersaoDocumento doc={self.documento_id} v{self.numero_versao}>"


class AnexoVersao(db.Model):
    """Arquivo adicional de uma versão de documento.

    Uma entrega costuma ser o texto e seus acompanhantes (dados, figuras, carta
    de encaminhamento). O primeiro arquivo enviado fica em `VersaoDocumento` —
    o principal —, os demais aqui. Sem principal não há anexo: a versão só
    comentário não tem arquivo algum. Mesmo armazenamento das versões."""

    __tablename__ = "anexo_versao"

    id = db.Column(db.Integer, primary_key=True)
    versao_id = db.Column(
        db.Integer, db.ForeignKey("versao_documento.id"), nullable=False
    )
    nome_original = db.Column(db.String(255), nullable=False)
    nome_fisico = db.Column(db.String(64), unique=True, nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)

    versao = db.relationship("VersaoDocumento", back_populates="anexos")

    def __repr__(self) -> str:
        return f"<AnexoVersao {self.id} versao={self.versao_id}>"


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
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    autor = db.relationship("Usuario", foreign_keys=[enviado_por])

    def __repr__(self) -> str:
        return f"<ModeloDocumento {self.id} {self.titulo!r}>"
