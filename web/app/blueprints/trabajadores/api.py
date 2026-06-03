# web/app/blueprints/trabajadores/api.py
from __future__ import annotations

import re

from flask import request
from flask_login import login_required, current_user
from sqlalchemy import and_, or_
import sqlalchemy as sa

from ...models import Trabajador, Contrato, Obra  # ajusta si cambia el path/relaciones
from ...auth.decorators import role_required

from .routes import bp  # ✅ IMPORTANTE: colgar del MISMO blueprint "trabajadores"


_RUT_CLEAN_RE = re.compile(r"[^0-9kK]")


def _split_rut(raw: str) -> tuple[str, str]:
    if not raw:
        return "", ""
    cleaned = _RUT_CLEAN_RE.sub("", str(raw)).upper()
    if len(cleaned) < 2:
        return "", ""
    dv = cleaned[-1]
    rut_digits = re.sub(r"\D", "", cleaned[:-1])
    if not rut_digits:
        return "", ""
    if not (dv.isdigit() or dv == "K"):
        return "", ""
    return rut_digits, dv


def _centros_costos_user() -> list[str]:
    """Centros de costo accesibles para usuario no ADMIN (si existe relación current_user.obras)."""
    if getattr(current_user, "has_role", None) and current_user.has_role("ADMIN"):
        return []
    ccs: list[str] = []
    for o in (getattr(current_user, "obras", None) or []):
        cc = (getattr(o, "centro_costo", "") or "").strip()
        if cc and (getattr(o, "estado", "") or "").upper() == "ACTIVA":
            ccs.append(cc)
    return sorted(set(ccs))


@bp.get("/api/trabajadores/search")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def api_search_trabajadores():
    """
    Endpoint corporativo de búsqueda/autocomplete de trabajadores.
    Ruta final: /trabajadores/api/trabajadores/search
    Params:
      - q (min 2)
      - limit (opcional, default 20, max 50)
      - include_no_vigente (0/1) default 1
    """
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return {"results": []}

    limit = request.args.get("limit", type=int) or 20
    limit = max(1, min(limit, 50))

    include_no_vigente = (request.args.get("include_no_vigente") or "1").strip() != "0"

    tokens = [t for t in re.split(r"\s+", q) if t]
    rut_digits, dv = _split_rut(q)

    query = Trabajador.query

    # ✅ Control acceso (no ADMIN): restringimos por contratos->obra->centro_costo
    if getattr(current_user, "has_role", None) and not current_user.has_role("ADMIN"):
        ccs = _centros_costos_user()
        if not ccs:
            return {"results": []}

        query = (
            query.join(Contrato, Contrato.trabajador_id == Trabajador.id)
                 .join(Obra, Obra.id == Contrato.obra_id)
                 .filter(Obra.centro_costo.in_(ccs))
        )

    # ✅ Filtro estado trabajador (si existe campo)
    if not include_no_vigente and hasattr(Trabajador, "estado_trabajador"):
        query = query.filter(Trabajador.estado_trabajador == "VIGENTE")

    # ✅ Predicados por tokens (AND de ORs)
    preds = []
    for tok in tokens:
        like = f"%{tok}%"
        tok_digits = re.sub(r"\D", "", tok)

        ors = [
            Trabajador.nombres.ilike(like),
            Trabajador.ap_paterno.ilike(like),
            Trabajador.ap_materno.ilike(like),
        ]

        if hasattr(Trabajador, "rut"):
            ors.append(sa.cast(Trabajador.rut, sa.String).ilike(like))
        if hasattr(Trabajador, "dv"):
            ors.append(Trabajador.dv.ilike(like))
        if tok_digits and hasattr(Trabajador, "rut"):
            ors.append(sa.cast(Trabajador.rut, sa.String).ilike(f"%{tok_digits}%"))

        preds.append(or_(*ors))

    if preds:
        query = query.filter(and_(*preds))

    # ✅ RUT “fuerte”
    if rut_digits and hasattr(Trabajador, "rut"):
        query = query.filter(sa.cast(Trabajador.rut, sa.String).ilike(f"%{rut_digits}%"))
    if dv and hasattr(Trabajador, "dv"):
        query = query.filter(Trabajador.dv.ilike(f"%{dv}%"))

    # ✅ Evitar duplicados por joins
    query = query.distinct()

    # Orden corporativo
    query = query.order_by(
        Trabajador.ap_paterno.asc().nullslast(),
        Trabajador.ap_materno.asc().nullslast(),
        Trabajador.nombres.asc().nullslast(),
        Trabajador.id.asc(),
    ).limit(limit)

    results = []
    for t in query.all():
        estado = (getattr(t, "estado_trabajador", "") or "").strip().upper()
        rut_txt = getattr(t, "rut_completo", "") or ""

        # formato corporativo: Apellido Apellido, Nombres
        nombre = f"{t.ap_paterno or ''} {t.ap_materno or ''}, {t.nombres or ''}".strip().strip(",")

        badge = ""
        if estado and estado != "VIGENTE":
            badge = " · NO VIGENTE"

        results.append({
            "id": t.id,
            "rut": rut_txt,
            "nombre": nombre,
            "estado": estado,
            "label": f"{nombre} · {rut_txt}{badge}".strip(" ·"),
        })

    return {"results": results}