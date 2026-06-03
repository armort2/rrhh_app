# web/app/services/rut_format.py
from __future__ import annotations

import re


def rut_con_puntos(rut: str | None) -> str:
    """
    Convierte '16232010-6' o '162320106' a '16.232.010-6'.
    Si viene vacío o no parseable, devuelve '' o el original limpio.
    """
    if not rut:
        return ""

    s = rut.strip().upper()
    s = s.replace(" ", "")

    # Si viene con formato XXXXXX-X, separamos
    if "-" in s:
        num, dv = s.split("-", 1)
    else:
        # Si viene pegado, el último char es DV
        m = re.match(r"^(\d+)([0-9K])$", s)
        if m:
            num, dv = m.group(1), m.group(2)
        else:
            # No sabemos parsear: devolvemos tal cual (pero sin espacios)
            return s

    num = re.sub(r"\D", "", num)
    dv = re.sub(r"[^0-9K]", "", dv)[:1]

    if not num or not dv:
        return s

    # puntos miles
    rev = num[::-1]
    chunks = [rev[i:i+3] for i in range(0, len(rev), 3)]
    num_puntos = ".".join(c[::-1] for c in chunks[::-1])

    return f"{num_puntos}-{dv}"