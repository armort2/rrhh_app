from flask import Blueprint

bp = Blueprint(
    "cumplimiento_laboral",
    __name__,
    url_prefix="/cumplimiento-laboral",
)

from . import routes  # noqa
