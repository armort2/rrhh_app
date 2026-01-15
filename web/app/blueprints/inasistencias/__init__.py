from flask import Blueprint

bp = Blueprint("inasistencias", __name__, url_prefix="/inasistencias")

from . import routes  # noqa
