from flask import Blueprint

bp = Blueprint("anticipos", __name__, url_prefix="/anticipos")

from . import routes  # noqa: F401
