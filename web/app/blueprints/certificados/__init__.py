# web/app/blueprints/certificados/__init__.py
from flask import Blueprint

bp = Blueprint("certificados", __name__, url_prefix="/certificados")

from . import routes  # noqa