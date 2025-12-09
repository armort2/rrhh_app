# web/app/blueprints/documentos/__init__.py

from flask import Blueprint

documentos_bp = Blueprint(
    "documentos",
    __name__,
    url_prefix="/documentos"
)

from . import routes  # noqa
