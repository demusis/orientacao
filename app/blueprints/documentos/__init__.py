from flask import Blueprint

bp = Blueprint("documentos", __name__)

from app.blueprints.documentos import routes  # noqa: E402,F401
