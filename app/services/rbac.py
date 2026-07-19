"""Controle de acesso: papel (decorator) + propriedade do recurso (helpers)."""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Orientacao, OrientacaoOrientador


def role_required(*papeis):
    """Restringe a view aos papéis informados. Admin não é implícito:
    inclua 'admin' explicitamente quando aplicável."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.papel not in papeis:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def orientacao_autorizada(orientacao_id: int) -> Orientacao:
    """Carrega a orientação e valida a propriedade do recurso.
    Admin acessa qualquer orientação; orientador/orientando apenas as próprias."""
    orientacao = db.session.get(Orientacao, orientacao_id)
    if orientacao is None:
        abort(404)
    if current_user.papel != "admin" and not orientacao.envolve(current_user):
        abort(403)
    return orientacao


def orientacoes_do_usuario():
    """Consulta-base de orientações visíveis ao usuário corrente. Orientador
    enxerga vínculos em que é principal ou coorientador."""
    q = Orientacao.query
    if current_user.papel == "orientador":
        return (
            q.outerjoin(
                OrientacaoOrientador,
                OrientacaoOrientador.orientacao_id == Orientacao.id,
            )
            .filter(
                or_(
                    Orientacao.orientador_id == current_user.id,
                    OrientacaoOrientador.usuario_id == current_user.id,
                )
            )
            .distinct()
        )
    if current_user.papel == "orientando":
        return q.filter_by(orientando_id=current_user.id)
    return q  # admin
