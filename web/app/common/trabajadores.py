# web/app/common/trabajadores.py
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import or_, func, cast, String

from ..models import Contrato, Trabajador
from .rut import rut_con_puntos


def normalizar_busqueda(texto: str | None) -> str:
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def tokens_busqueda(texto: str | None) -> list[str]:
    texto = normalizar_busqueda(texto)
    if not texto:
        return []

    raw_tokens = texto.replace(".", "").replace("-", "").split()
    return [token for token in raw_tokens if token]


def _campo_texto_sin_tildes(campo):
    """
    Normaliza una columna de texto en PostgreSQL:
    lower(unaccent(campo))
    """
    return func.lower(func.unaccent(campo))


def query_contratos_selector(user, q: str | None = None, limit: int = 25, solo_vigentes: bool = True):
    tokens = tokens_busqueda(q)

    query = (
        Contrato.query
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
    )

    if solo_vigentes and hasattr(Contrato, "estado_contrato"):
        query = query.filter(Contrato.estado_contrato == "VIGENTE")

    if user and not user.has_role("ADMIN"):
        obra_ids = [obra.id for obra in getattr(user, "obras", []) or []]
        query = query.filter(Contrato.obra_id.in_(obra_ids or [-1]))

    for token in tokens:
        like = f"%{token}%"

        rut_limpio = func.replace(
            func.replace(
                func.coalesce(Trabajador.rut, ""),
                ".",
                "",
            ),
            "-",
            "",
        )

        condiciones = [
            _campo_texto_sin_tildes(func.coalesce(Trabajador.nombres, "")).ilike(like),
            _campo_texto_sin_tildes(func.coalesce(Trabajador.ap_paterno, "")).ilike(like),
            _campo_texto_sin_tildes(func.coalesce(Trabajador.ap_materno, "")).ilike(like),
            rut_limpio.ilike(like),
        ]

        if token.isdigit():
            condiciones.append(Contrato.id == int(token))
            condiciones.append(cast(Contrato.id, String).ilike(like))

        query = query.filter(or_(*condiciones))

    return (
        query
        .order_by(
            Trabajador.ap_paterno.asc(),
            Trabajador.ap_materno.asc(),
            Trabajador.nombres.asc(),
            Contrato.id.desc(),
        )
        .limit(limit)
    )


def contrato_selector_payload(contrato) -> dict:
    trabajador = getattr(contrato, "trabajador", None)
    obra = getattr(contrato, "obra", None)
    cargo = getattr(contrato, "cargo", None)
    empleador = getattr(contrato, "empleador", None)

    nombres = getattr(trabajador, "nombres", "") or ""
    ap_paterno = getattr(trabajador, "ap_paterno", "") or ""
    ap_materno = getattr(trabajador, "ap_materno", "") or ""
    rut = getattr(trabajador, "rut", "") or ""

    trabajador_nombre = " ".join(
        part for part in [ap_paterno, ap_materno, nombres] if part
    ).strip()

    empleador_nombre = (
        getattr(empleador, "razon_social", None)
        or getattr(empleador, "nombre", None)
        or ""
    )

    return {
        "id": contrato.id,
        "contrato_id": contrato.id,
        "trabajador_id": contrato.trabajador_id,
        "obra_id": contrato.obra_id,
        "cargo_id": getattr(contrato, "cargo_id", None),
        "empleador_id": getattr(contrato, "empleador_id", None),
        "trabajador_nombre": trabajador_nombre or "Trabajador sin nombre",
        "trabajador_rut": rut_con_puntos(rut),
        "obra_nombre": getattr(obra, "nombre", None) or "Sin obra",
        "cargo_nombre": getattr(cargo, "nombre", None) or "Sin cargo",
        "empleador_nombre": empleador_nombre or "Sin empleador",
        "fecha_inicio": contrato.fecha_inicio.isoformat() if getattr(contrato, "fecha_inicio", None) else "",
        "fecha_termino": contrato.fecha_termino.isoformat() if getattr(contrato, "fecha_termino", None) else "",
        "estado_contrato": getattr(contrato, "estado_contrato", "") or "",
    }
