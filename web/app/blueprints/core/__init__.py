# web/app/blueprints/core/__init__.py

from flask import Blueprint

bp = Blueprint("core", __name__)

from . import routes  # noqa
