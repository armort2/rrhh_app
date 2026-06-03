# web/app/blueprints/prevencion_riesgos/validators.py
from __future__ import annotations


def validar_obra_accesible(user, obra_id: int | None) -> bool:
    if obra_id is None:
        return True
    if user.has_role("ADMIN"):
        return True
    return user.can_access_obra(obra_id)
