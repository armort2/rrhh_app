# web/app/blueprints/__init__.py

"""
Paquete de blueprints de la aplicación.

Este módulo únicamente re-exporta los blueprints ya definidos
en cada submódulo, para que puedan ser importados desde
`app.blueprints`.
"""
from __future__ import annotations

from .core import bp as core_bp
from .trabajadores import bp as trabajadores_bp
from .contratos import bp as contratos_bp
from .obras import bp as obras_bp
from .admin import bp as admin_bp
from .anexos import bp as anexos_bp
from .anexos_indefinidos import bp as anexos_indefinidos_bp
from .terceros import bp as terceros_bp
from .solicitudes_fondos import bp as solicitudes_fondos_bp

__all__ = [
    "core_bp",
    "trabajadores_bp",
    "contratos_bp",
    "obras_bp",
    "admin_bp",
    "anexos_bp",
    "anexos_indefinidos_bp",
    "terceros_bp",
    "solicitudes_fondos_bp",
]