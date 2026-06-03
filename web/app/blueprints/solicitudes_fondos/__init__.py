# web/app/blueprints/solicitudes_fondos/__init__.py
from __future__ import annotations
from flask import Blueprint

bp = Blueprint("solicitudes_fondos", __name__, url_prefix="/solicitudes-fondos")

from . import routes  # noqa: E402,F401