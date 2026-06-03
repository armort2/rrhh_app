# web/app/blueprints/contratos_vencimientos/__init__.py
from flask import Blueprint

bp = Blueprint(
    "contratos_vencimientos",
    __name__,
    url_prefix="/contratos/vencimientos",
)

from . import routes  # noqa