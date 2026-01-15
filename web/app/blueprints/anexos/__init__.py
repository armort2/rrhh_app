# web/app/blueprints/anexos/__init__.py

from flask import Blueprint

bp = Blueprint("anexos", __name__, url_prefix="/anexos")

from . import routes  # noqa
