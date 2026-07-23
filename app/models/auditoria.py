import json
from datetime import UTC, datetime

from app.extensions import db

# Rótulos em português para as chaves que a trilha grava em dados_json. Chave
# não prevista cai no fallback humanizado (ver dados_itens), de modo que uma
# chave nova nunca quebra a apresentação — apenas aparece menos polida.
CHAVE_DADO_LABEL = {
    "email": "E-mail",
    "grupo_id": "Grupo",
    "marcos": "Marcos",
    "orientacoes": "Orientações",
    "orientacao_id": "Orientação",
    "titulo": "Título",
    "tipo": "Tipo",
    "papel": "Papel",
    "documento_id": "Documento",
    "arquivo": "Arquivo",
    "versao": "Versão",
    "resultado": "Resultado",
    "removidos": "Removidos",
    "presenca": "Presença",
    "para": "Para",
    "de": "De",
    "motivo": "Motivo",
    "evento_id": "Evento",
    "usuario_id": "Usuário",
    "conta_preservada": "Conta preservada",
    "com_historico": "Com histórico",
    "ativo": "Ativo",
}


def _formatar_valor(valor):
    """Torna um valor do dados_json apresentável em uma linha."""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if valor is None or valor == "" or valor == []:
        return "(vazio)"
    if isinstance(valor, list):
        # listas de identificadores inteiros ganham o prefixo # (ex.: #12, #13)
        if all(isinstance(v, int) and not isinstance(v, bool) for v in valor):
            return ", ".join(f"#{v}" for v in valor)
        return ", ".join(str(v) for v in valor)
    return str(valor)


class LogAuditoria(db.Model):
    """Trilha append-only. A aplicação não expõe UPDATE/DELETE sobre esta tabela;
    toda escrita ocorre exclusivamente via services/auditoria.py."""

    __tablename__ = "log_auditoria"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    acao = db.Column(db.String(100), nullable=False)
    entidade = db.Column(db.String(50), nullable=False)
    entidade_id = db.Column(db.Integer, nullable=True)
    dados_json = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    usuario = db.relationship("Usuario")

    @property
    def dados(self):
        """O dados_json desserializado, ou None se ausente/ilegível."""
        if not self.dados_json:
            return None
        try:
            return json.loads(self.dados_json)
        except (ValueError, TypeError):
            return None

    @property
    def dados_itens(self):
        """Pares (rótulo, valor formatado) para exibição na trilha. Vazio quando
        os dados não são um objeto — nesse caso o template exibe o texto cru."""
        dados = self.dados
        if not isinstance(dados, dict):
            return []
        return [
            (
                CHAVE_DADO_LABEL.get(chave, chave.replace("_", " ").capitalize()),
                _formatar_valor(valor),
            )
            for chave, valor in dados.items()
        ]

    def __repr__(self) -> str:
        return f"<LogAuditoria {self.acao} {self.entidade}#{self.entidade_id}>"
