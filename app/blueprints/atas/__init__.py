from flask import Blueprint

bp = Blueprint("atas", __name__)

from app.blueprints.atas import routes  # noqa: E402,F401
