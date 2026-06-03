# web/app/blueprints/pago_proveedores/__init__.py
from flask import Blueprint

bp = Blueprint(
    "pago_proveedores",
    __name__,
    url_prefix="/pago-proveedores",
)

from . import routes  # noqa