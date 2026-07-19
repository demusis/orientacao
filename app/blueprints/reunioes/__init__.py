from flask import Blueprint

bp = Blueprint("reunioes", __name__)

from app.blueprints.reunioes import routes  # noqa: E402,F401
