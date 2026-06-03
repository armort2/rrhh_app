# web/app/blueprints/vacaciones/__init__.py
from flask import Blueprint

bp = Blueprint("vacaciones", __name__, url_prefix="/vacaciones")

from . import routes  # noqa
