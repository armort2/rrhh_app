# web/app/blueprints/extras_remuneracion/__init__.py
from flask import Blueprint

bp = Blueprint(
    "extras_remuneracion",
    __name__,
    url_prefix="/extras-remu",
)

# IMPORTANTÍSIMO: carga las rutas para que se registren los endpoints
from . import routes  # noqa: E402, F401