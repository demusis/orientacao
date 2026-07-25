"""Configurações editáveis pelo administrador, em linha única (`id=1`).

Ficam no banco, e não em variável de ambiente, para que a alteração não
dependa de acesso ao console do servidor. A senha de e-mail é guardada
cifrada (`services/cripto.py`) e **nunca** é devolvida à tela: o formulário a
recebe em branco e só a substitui quando algo é digitado.
"""
import json
from datetime import UTC, datetime

from app.extensions import db

# padrões do sinal de risco do prazo; valem enquanto o administrador não gravar
# a linha de configuração — ausência de linha significa exatamente estes valores
LIMIAR_MEDIO_PADRAO = 75
LIMIAR_ALTO_PADRAO = 90
TIPOS_CRITICOS_PADRAO = ("qualificacao", "defesa")


class ConfiguracaoEmail(db.Model):
    __tablename__ = "configuracao_email"

    id = db.Column(db.Integer, primary_key=True)
    ativo = db.Column(db.Boolean, nullable=False, default=False)
    servidor = db.Column(db.String(255), nullable=False, default="smtp.gmail.com")
    porta = db.Column(db.Integer, nullable=False, default=587)
    usuario = db.Column(db.String(254), nullable=False, default="")
    # senha de app do Google, cifrada; ver services/cripto.py quanto ao alcance
    senha_cifrada = db.Column(db.Text, nullable=True)
    remetente_nome = db.Column(db.String(120), nullable=False, default="ARIADNE")
    # Dia em que os avisos foram entregues com sucesso. Só avança quando ao
    # menos uma mensagem chega ao servidor SMTP — lote que falha por rede não
    # consome o disparo do dia.
    avisos_enviados_em = db.Column(db.Date, nullable=True)
    # Instante da última tentativa (UTC ingênuo, como o resto do banco). Sustenta
    # a trava contra disparo concorrente e o intervalo entre repetições: sem ele,
    # rede instável faria toda requisição tentar de novo.
    avisos_tentados_em = db.Column(db.DateTime, nullable=True)
    # JSON {"dia": "AAAA-MM-DD", "emails": [...]} com quem já recebeu no dia.
    # É o que permite repetir uma tentativa parcialmente falha sem reenviar a
    # quem já foi atendido — sem isto, ou se abandonava o destinatário que
    # falhou, ou se duplicava a mensagem dos demais.
    avisos_entregues = db.Column(db.Text, nullable=True)
    atualizado_em = db.Column(db.DateTime, nullable=True)
    atualizado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)

    autor = db.relationship("Usuario", foreign_keys=[atualizado_por])

    @classmethod
    def vigente(cls) -> "ConfiguracaoEmail":
        """Devolve a linha única, criando-a na primeira consulta. Evita que toda
        chamada precise tratar o caso 'ainda não configurado'."""
        config = db.session.get(cls, 1)
        if config is None:
            config = cls(id=1)
            db.session.add(config)
            db.session.flush()
        return config

    @property
    def configurado(self) -> bool:
        return bool(self.usuario and self.senha_cifrada)

    @property
    def operante(self) -> bool:
        """Pronto para enviar: configurado e habilitado pelo administrador."""
        return self.configurado and self.ativo

    def registrar_alteracao(self, usuario_id: int) -> None:
        self.atualizado_em = datetime.now(UTC)
        self.atualizado_por = usuario_id

    def __repr__(self) -> str:
        return f"<ConfiguracaoEmail {self.usuario!r} ativo={self.ativo}>"


class ConfiguracaoRisco(db.Model):
    """Parâmetros do sinal de risco do prazo (`painel.relogio`): os limiares
    percentuais que mudam a cor do selo e os tipos de marco cujo atraso acende
    o vermelho independentemente do tempo decorrido."""

    __tablename__ = "configuracao_risco"

    id = db.Column(db.Integer, primary_key=True)
    # percentuais do prazo decorrido: acima do médio o selo fica amarelo,
    # acima do alto, vermelho
    limiar_medio = db.Column(db.Integer, nullable=False, default=LIMIAR_MEDIO_PADRAO)
    limiar_alto = db.Column(db.Integer, nullable=False, default=LIMIAR_ALTO_PADRAO)
    # lista JSON de tipos de marco (TIPOS_MARCO) considerados críticos
    tipos_criticos = db.Column(
        db.Text,
        nullable=False,
        default=lambda: json.dumps(list(TIPOS_CRITICOS_PADRAO)),
    )
    atualizado_em = db.Column(db.DateTime, nullable=True)
    atualizado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)

    autor = db.relationship("Usuario", foreign_keys=[atualizado_por])

    @classmethod
    def vigente(cls) -> "ConfiguracaoRisco":
        """Devolve a linha única ou, se nunca gravada, um objeto com os padrões
        **fora da sessão**: o caminho de leitura (o relógio do painel, a cada
        vínculo listado) não deve gravar nada. Quem grava é a tela do
        administrador, que faz `db.session.add` e comita."""
        return db.session.get(cls, 1) or cls(
            id=1,
            limiar_medio=LIMIAR_MEDIO_PADRAO,
            limiar_alto=LIMIAR_ALTO_PADRAO,
            tipos_criticos=json.dumps(list(TIPOS_CRITICOS_PADRAO)),
        )

    @property
    def criticos(self) -> tuple[str, ...]:
        return tuple(json.loads(self.tipos_criticos))

    def definir_criticos(self, tipos) -> None:
        """Grava na ordem canônica de TIPOS_MARCO, ignorando valor desconhecido:
        a tela só oferece os tipos válidos, mas o POST é texto livre."""
        from app.models.cronograma import TIPOS_MARCO

        recebidos = set(tipos)
        self.tipos_criticos = json.dumps([t for t in TIPOS_MARCO if t in recebidos])

    def registrar_alteracao(self, usuario_id: int) -> None:
        self.atualizado_em = datetime.now(UTC)
        self.atualizado_por = usuario_id

    def __repr__(self) -> str:
        return (
            f"<ConfiguracaoRisco {self.limiar_medio}/{self.limiar_alto} "
            f"{self.criticos!r}>"
        )
