# web/app/blueprints/__init__.py

"""
Paquete de blueprints de la aplicación.

Este módulo únicamente re-exporta los blueprints ya definidos
en cada submódulo, para que puedan ser importados desde
`app.blueprints`.
"""

from .core import bp as core_bp
from .trabajadores import bp as trabajadores_bp
from .contratos import bp as contratos_bp
from .obras import bp as obras_bp
