# web/app/services/date_format.py
from __future__ import annotations

from datetime import date

_MESES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

def fecha_larga_el(d: date | None) -> str:
    """
    Retorna: 'el 01 de febrero de 2026'
    (con 0 a la izquierda, como documento formal).
    """
    if not d:
        return ""
    mes = _MESES.get(d.month, "")
    return f"el {d.day:02d} de {mes} de {d.year}"