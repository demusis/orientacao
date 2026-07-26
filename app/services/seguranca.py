"""Limite de tentativas de autenticação, apoiado na trilha de auditoria.

Sem tabela nova: a trilha já registra cada `login_falho` com `ip` e `timestamp`,
que é tudo o que uma contagem por origem precisa.

**Alcance, declarado.** Contém a força bruta comum — muitas tentativas de um
mesmo endereço. **Não** cobre ataque distribuído contra uma conta específica,
com um IP por tentativa; para isso seria preciso contar por conta, o que
transformaria o mecanismo em vetor de bloqueio de vítima (basta o atacante errar
a senha de alguém para trancá-lo). A escolha por origem é deliberada, e a
limitação está registrada em `avaliacoes/DECISOES.md`.
"""
from datetime import timedelta

from flask import current_app, request
from sqlalchemy import func

from app.extensions import db
from app.models import LogAuditoria
from app.services.tempo import agora

# Ações de autenticação que contam para o limite por origem. As falhas, pela
# força bruta; e também o pedido de recuperação BEM-SUCEDIDO: cada um envia um
# e-mail real, e sem contá-lo um único IP podia inundar a caixa da vítima e
# esgotar a cota diária de envio do sistema repetindo /auth/esqueci com um
# e-mail válido — as falhas limitavam só quem errava o endereço.
ACOES_LIMITADAS = ("login_falho", "recuperacao_falha", "recuperacao_solicitada")


def excedeu_tentativas() -> bool:
    """True se a origem atual estourou o teto na janela configurada.

    A origem é `request.remote_addr`, já ajustado por ProxyFix conforme
    `TRUSTED_PROXY_COUNT` — o mesmo endereço que a auditoria grava, de modo que
    contagem e registro falam da mesma coisa."""
    janela = current_app.config["LOGIN_JANELA_MINUTOS"]
    teto = current_app.config["LOGIN_MAX_TENTATIVAS"]
    desde = agora() - timedelta(minutes=janela)

    quantas = (
        db.session.query(func.count(LogAuditoria.id))
        .filter(
            LogAuditoria.acao.in_(ACOES_LIMITADAS),
            LogAuditoria.ip == request.remote_addr,
            LogAuditoria.timestamp >= desde,
        )
        .scalar()
    )
    return quantas >= teto
