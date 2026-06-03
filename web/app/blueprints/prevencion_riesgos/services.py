# web/app/blueprints/prevencion_riesgos/services.py
from __future__ import annotations

from ...extensions import db
from ...models import PrevTipoEPP
from .constants import TIPOS_EPP_INICIALES


def seed_tipos_epp_iniciales() -> int:
    creados = 0

    for item in TIPOS_EPP_INICIALES:
        nombre = item["nombre"]
        exists = PrevTipoEPP.query.filter_by(nombre=nombre).first()
        if exists:
            continue

        tipo = PrevTipoEPP(
            nombre=nombre,
            requiere_talla=bool(item.get("requiere_talla")),
            requiere_reposicion=bool(item.get("requiere_reposicion")),
            dias_reposicion_sugerida=item.get("dias_reposicion_sugerida"),
            activo=True,
        )
        db.session.add(tipo)
        creados += 1

    if creados:
        db.session.commit()

    return creados
