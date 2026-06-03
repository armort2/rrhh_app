# web/app/blueprints/desvinculaciones/__init__.py
from flask import Blueprint

bp = Blueprint("desvinculaciones", __name__, url_prefix="/desvinculaciones")

from . import routes  # noqa: F401
