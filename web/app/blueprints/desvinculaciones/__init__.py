from flask import Blueprint

bp = Blueprint("desvinculaciones", __name__, url_prefix="/desvinculaciones")

from . import routes  # noqa: F401
