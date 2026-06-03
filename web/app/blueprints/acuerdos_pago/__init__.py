# web/app/blueprints/acuerdos_pago/__init__.py
from flask import Blueprint

bp = Blueprint("acuerdos_pago", __name__, url_prefix="/acuerdos-pago")

from . import routes  # noqa