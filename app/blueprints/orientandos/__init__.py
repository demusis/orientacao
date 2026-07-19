from flask import Blueprint

bp = Blueprint("orientandos", __name__)

from app.blueprints.orientandos import routes  # noqa: E402,F401
