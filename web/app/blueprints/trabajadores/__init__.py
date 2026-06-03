# web/app/blueprints/trabajadores/__init__.py
from .routes import bp  # noqa: F401
from . import api  # noqa: F401  <-- IMPORTANTÍSIMO: fuerza import y registra endpoints