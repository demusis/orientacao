"""Ponto único de escrita da trilha de auditoria (risco R5)."""
import json

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import LogAuditoria


def registrar(
    acao: str,
    entidade: str,
    entidade_id=None,
    dados: dict | None = None,
    automatico: bool = False,
):
    """Adiciona um registro à trilha na sessão corrente (commit a cargo do chamador,
    para que o log participe da mesma transação da operação auditada).

    `automatico=True` para ato do próprio sistema, e não de uma pessoa: o autor e
    o IP ficam nulos, em vez de herdarem o usuário da requisição em curso. Sem
    isso, um disparo em segundo plano acionado pela visita de um orientando
    ficaria registrado como se ele o tivesse executado — corrompendo justamente a
    trilha que existe para atribuir responsabilidade."""
    usuario_id = None
    ip = None
    if has_request_context() and not automatico:
        ip = request.remote_addr
        if current_user.is_authenticated:
            usuario_id = current_user.id

    log = LogAuditoria(
        usuario_id=usuario_id,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        dados_json=json.dumps(dados, ensure_ascii=False, default=str) if dados else None,
        ip=ip,
    )
    db.session.add(log)
    return log
