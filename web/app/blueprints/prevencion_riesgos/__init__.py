# web/app/blueprints/prevencion_riesgos/__init__.py
from flask import Blueprint

bp = Blueprint(
    "prevencion_riesgos",
    __name__,
    url_prefix="/prevencion-riesgos",
)

from . import routes  # noqa
