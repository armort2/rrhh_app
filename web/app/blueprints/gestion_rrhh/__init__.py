# web/app/blueprints/gestion_rrhh/__init__.py
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("gestion_rrhh", __name__, url_prefix="/gestion-rrhh")

from . import routes  # noqa: E402,F401
