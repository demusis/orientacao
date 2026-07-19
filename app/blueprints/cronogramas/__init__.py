from flask import Blueprint

bp = Blueprint("cronogramas", __name__)

from app.blueprints.cronogramas import routes  # noqa: E402,F401
