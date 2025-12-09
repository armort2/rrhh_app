# web/app/blueprints/obras/__init__.py

from flask import Blueprint

bp = Blueprint("obras", __name__, url_prefix="/obras")

from . import routes  # noqa
