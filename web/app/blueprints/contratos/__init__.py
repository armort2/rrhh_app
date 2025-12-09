# web/app/blueprints/contratos/__init__.py

from flask import Blueprint

bp = Blueprint("contratos", __name__, url_prefix="/contratos")

from . import routes  # noqa
