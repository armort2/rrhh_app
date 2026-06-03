# web/app/blueprints/egresos/__init__.py
from flask import Blueprint

bp = Blueprint("egresos", __name__, url_prefix="/egresos")

from . import routes  # noqa