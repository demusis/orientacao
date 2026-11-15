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

PARAMETROS_MODELO_RISCO_PADRAO = {
    "peso_atraso": 30,
    "peso_ritmo": 30,
    "peso_criticos": 20,
    "peso_assiduidade": 20,
    "nota_risco_moderado": 25,
    "nota_risco_alto": 50,
    "nota_risco_critico": 75,
    "dias_atraso_grave": 30,
    "janela_marco_critico_dias": 30,
    "dias_inatividade_alerta": 45,
    "tolerancia_ausencia_pct": 25,
}


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

    def _carga_json(self) -> tuple[list[str], dict[str, int]]:
        if self.tipos_criticos is None:
            return (list(TIPOS_CRITICOS_PADRAO), dict(PARAMETROS_MODELO_RISCO_PADRAO))
        try:
            dados = json.loads(self.tipos_criticos or "[]")
        except (ValueError, TypeError):
            return (list(TIPOS_CRITICOS_PADRAO), dict(PARAMETROS_MODELO_RISCO_PADRAO))
        if isinstance(dados, dict):
            tipos = list(dados.get("tipos", TIPOS_CRITICOS_PADRAO))
            modelo_dados = dados.get("modelo")
            if isinstance(modelo_dados, dict):
                modelo = {**PARAMETROS_MODELO_RISCO_PADRAO, **modelo_dados}
            else:
                modelo = dict(PARAMETROS_MODELO_RISCO_PADRAO)
            return (tipos, modelo)
        if isinstance(dados, list):
            return (dados, dict(PARAMETROS_MODELO_RISCO_PADRAO))
        return (list(TIPOS_CRITICOS_PADRAO), dict(PARAMETROS_MODELO_RISCO_PADRAO))

    @property
    def criticos(self) -> tuple[str, ...]:
        return tuple(self._carga_json()[0])

    @property
    def parametros_modelo(self) -> dict[str, int]:
        return self._carga_json()[1]

    @property
    def peso_atraso(self) -> int:
        return int(self.parametros_modelo["peso_atraso"])

    @peso_atraso.setter
    def peso_atraso(self, valor: int) -> None:
        self.definir_parametros_modelo(peso_atraso=valor)

    @property
    def peso_ritmo(self) -> int:
        return int(self.parametros_modelo["peso_ritmo"])

    @peso_ritmo.setter
    def peso_ritmo(self, valor: int) -> None:
        self.definir_parametros_modelo(peso_ritmo=valor)

    @property
    def peso_criticos(self) -> int:
        return int(self.parametros_modelo["peso_criticos"])

    @peso_criticos.setter
    def peso_criticos(self, valor: int) -> None:
        self.definir_parametros_modelo(peso_criticos=valor)

    @property
    def peso_assiduidade(self) -> int:
        return int(self.parametros_modelo["peso_assiduidade"])

    @peso_assiduidade.setter
    def peso_assiduidade(self, valor: int) -> None:
        self.definir_parametros_modelo(peso_assiduidade=valor)

    @property
    def nota_risco_moderado(self) -> int:
        return int(self.parametros_modelo["nota_risco_moderado"])

    @nota_risco_moderado.setter
    def nota_risco_moderado(self, valor: int) -> None:
        self.definir_parametros_modelo(nota_risco_moderado=valor)

    @property
    def nota_risco_alto(self) -> int:
        return int(self.parametros_modelo["nota_risco_alto"])

    @nota_risco_alto.setter
    def nota_risco_alto(self, valor: int) -> None:
        self.definir_parametros_modelo(nota_risco_alto=valor)

    @property
    def nota_risco_critico(self) -> int:
        return int(self.parametros_modelo["nota_risco_critico"])

    @nota_risco_critico.setter
    def nota_risco_critico(self, valor: int) -> None:
        self.definir_parametros_modelo(nota_risco_critico=valor)

    @property
    def dias_atraso_grave(self) -> int:
        return int(self.parametros_modelo["dias_atraso_grave"])

    @dias_atraso_grave.setter
    def dias_atraso_grave(self, valor: int) -> None:
        self.definir_parametros_modelo(dias_atraso_grave=valor)

    @property
    def janela_marco_critico_dias(self) -> int:
        return int(self.parametros_modelo["janela_marco_critico_dias"])

    @janela_marco_critico_dias.setter
    def janela_marco_critico_dias(self, valor: int) -> None:
        self.definir_parametros_modelo(janela_marco_critico_dias=valor)

    @property
    def dias_inatividade_alerta(self) -> int:
        return int(self.parametros_modelo["dias_inatividade_alerta"])

    @dias_inatividade_alerta.setter
    def dias_inatividade_alerta(self, valor: int) -> None:
        self.definir_parametros_modelo(dias_inatividade_alerta=valor)

    @property
    def tolerancia_ausencia_pct(self) -> int:
        return int(self.parametros_modelo["tolerancia_ausencia_pct"])

    @tolerancia_ausencia_pct.setter
    def tolerancia_ausencia_pct(self, valor: int) -> None:
        self.definir_parametros_modelo(tolerancia_ausencia_pct=valor)

    def definir_criticos(self, tipos) -> None:
        """Grava na ordem canônica de TIPOS_MARCO, ignorando valor desconhecido:
        a tela só oferece os tipos válidos, mas o POST é texto livre."""
        from app.models.cronograma import TIPOS_MARCO

        recebidos = set(tipos)
        lista_tipos = [t for t in TIPOS_MARCO if t in recebidos]
        atuais = self.parametros_modelo
        if atuais == PARAMETROS_MODELO_RISCO_PADRAO:
            self.tipos_criticos = json.dumps(lista_tipos)
        else:
            self.tipos_criticos = json.dumps(
                {"tipos": lista_tipos, "modelo": atuais}, ensure_ascii=False
            )

    def definir_parametros_modelo(self, **novos) -> None:
        tipos_atuais = list(self.criticos)
        atuais = dict(self.parametros_modelo)
        atuais.update(
            {
                k: int(v)
                for k, v in novos.items()
                if k in PARAMETROS_MODELO_RISCO_PADRAO and v is not None
            }
        )
        if atuais == PARAMETROS_MODELO_RISCO_PADRAO:
            self.tipos_criticos = json.dumps(tipos_atuais)
        else:
            self.tipos_criticos = json.dumps(
                {"tipos": tipos_atuais, "modelo": atuais}, ensure_ascii=False
            )

    def registrar_alteracao(self, usuario_id: int) -> None:
        self.atualizado_em = datetime.now(UTC)
        self.atualizado_por = usuario_id

    def __repr__(self) -> str:
        return (
            f"<ConfiguracaoRisco {self.limiar_medio}/{self.limiar_alto} "
            f"{self.criticos!r}>"
        )
