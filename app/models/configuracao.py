"""Configuração de envio de e-mail, editável pelo administrador.

Linha única (`id=1`). Fica no banco, e não em variável de ambiente, para que a
alteração não dependa de acesso ao console do servidor. A senha é guardada
cifrada (`services/cripto.py`) e **nunca** é devolvida à tela: o formulário a
recebe em branco e só a substitui quando algo é digitado.
"""
from datetime import UTC, datetime

from app.extensions import db


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
