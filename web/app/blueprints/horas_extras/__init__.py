# web/app/blueprints/horas_extras/__init__.py
from flask import Blueprint

bp = Blueprint("horas_extras", __name__, url_prefix="/horas-extras")

from . import routes  # noqa: E402,F401
