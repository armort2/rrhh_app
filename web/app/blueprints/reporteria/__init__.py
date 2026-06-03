from flask import Blueprint

bp = Blueprint("reporteria", __name__, url_prefix="/reporteria")

from . import routes  # noqa: E402,F401
