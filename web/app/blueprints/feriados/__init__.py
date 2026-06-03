# web/app/blueprints/feriados/__init__.py
from flask import Blueprint

bp = Blueprint("feriados", __name__, url_prefix="/feriados")

from . import routes  # noqa: E402,F401
