# web/app/blueprints/terceros/__init__.py
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("terceros", __name__, url_prefix="/terceros")

from . import routes  # noqa: E402,F401