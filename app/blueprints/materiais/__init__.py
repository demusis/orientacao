from flask import Blueprint

bp = Blueprint("materiais", __name__)

from app.blueprints.materiais import routes  # noqa: E402,F401
