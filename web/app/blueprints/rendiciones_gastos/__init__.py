# web/app/blueprints/rendiciones_gastos/__init__.py
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("rendiciones_gastos", __name__, url_prefix="/rendiciones-gastos")

from . import routes  # noqa: E402,F401
