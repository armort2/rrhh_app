# web/app/blueprints/anexos_indefinidos/__init__.py
from flask import Blueprint

bp = Blueprint(
    "anexos_indefinidos",
    __name__,
    url_prefix="/anexos-indefinidos",
)

from . import routes  # noqa: E402,F401
