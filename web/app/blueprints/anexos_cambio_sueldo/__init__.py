# web/app/blueprints/anexos_cambio_sueldo/__init__.py

from flask import Blueprint

bp = Blueprint("anexos_cambio_sueldo", __name__, url_prefix="/anexos-cambio-sueldo")

from . import routes  # noqa: E402,F401
