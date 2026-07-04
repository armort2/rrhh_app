"""
Utilidades comunes del Sistema Grupo CS.

Este paquete centraliza helpers transversales para evitar duplicidad
entre blueprints y servicios.
"""

from .navigation import is_safe_redirect_target, safe_next_from_request, safe_next_url  # noqa: F401
