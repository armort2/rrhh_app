# web/app/blueprints/transferencias_bancarias/__init__.py
from __future__ import annotations
from flask import Blueprint

bp = Blueprint(
    "transferencias_bancarias",
    __name__,
    url_prefix="/transferencias-bancarias",
)

from . import routes  # noqa: E402,F401