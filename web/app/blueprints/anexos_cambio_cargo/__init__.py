# web/app/blueprints/anexos_cambio_cargo/__init__.py

from flask import Blueprint

bp = Blueprint("anexos_cambio_cargo", __name__, url_prefix="/anexos-cambio-cargo")

from . import routes  # noqa: E402,F401
