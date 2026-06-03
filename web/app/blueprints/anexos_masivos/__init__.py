# web/app/blueprints/anexos_masivos/__init__.py
from flask import Blueprint

bp = Blueprint(
    "anexos_masivos",
    __name__,
    url_prefix="/anexos-masivos",
)

from . import routes  # noqa: E402,F401