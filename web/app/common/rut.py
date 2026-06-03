# web/app/common/rut.py
from __future__ import annotations

import re


def clean_rut(value) -> str:
    """
    Limpia un RUT dejando solo números y K.
    """
    if value is None:
        return ""

    value = str(value).strip().upper()
    value = value.replace(".", "").replace("-", "")
    value = re.sub(r"[^0-9K]", "", value)
    return value


def calcular_dv(cuerpo: str | int | None) -> str:
    """
    Calcula dígito verificador chileno para el cuerpo del RUT.
    """
    cuerpo_limpio = re.sub(r"[^0-9]", "", str(cuerpo or ""))

    if not cuerpo_limpio:
        return ""

    suma = 0
    multiplicador = 2

    for digito in reversed(cuerpo_limpio):
        suma += int(digito) * multiplicador
        multiplicador += 1
        if multiplicador > 7:
            multiplicador = 2

    resto = suma % 11
    dv_num = 11 - resto

    if dv_num == 11:
        return "0"
    if dv_num == 10:
        return "K"
    return str(dv_num)


def split_rut(value):
    """
    Retorna una tupla (cuerpo, dv).

    Reglas:
    - Si viene con guion explícito, respeta cuerpo y DV indicado.
    - Si viene sin guion y el último carácter genera un RUT válido, lo interpreta como RUT completo.
    - Si viene sin guion y NO genera un RUT válido, interpreta todo como cuerpo y calcula el DV.
    """
    if value is None:
        return "", ""

    raw = str(value).strip().upper()

    if not raw:
        return "", ""

    # Caso explícito: 12.345.678-5
    if "-" in raw:
        parts = raw.replace(".", "").split("-")
        cuerpo = re.sub(r"[^0-9]", "", parts[0] if parts else "")
        dv = re.sub(r"[^0-9K]", "", parts[1] if len(parts) > 1 else "")
        return cuerpo, dv[:1]

    cleaned = clean_rut(raw)

    if not cleaned:
        return "", ""

    # Si trae cuerpo + DV y calza, lo respetamos.
    if len(cleaned) >= 2:
        posible_cuerpo = cleaned[:-1]
        posible_dv = cleaned[-1]

        if calcular_dv(posible_cuerpo) == posible_dv:
            return posible_cuerpo, posible_dv

    # Si no calza, asumimos que viene solo el cuerpo y calculamos DV.
    cuerpo = re.sub(r"[^0-9]", "", cleaned)
    return cuerpo, calcular_dv(cuerpo)


def rut_compacto(value) -> str:
    """
    Retorna RUT como 12345678-5.
    """
    cuerpo, dv = split_rut(value)

    if not cuerpo:
        return ""

    if not dv:
        dv = calcular_dv(cuerpo)

    return f"{cuerpo}-{dv}"


def rut_con_puntos(value) -> str:
    """
    Retorna RUT como 12.345.678-5.
    """
    cuerpo, dv = split_rut(value)

    if not cuerpo:
        return ""

    if not dv:
        dv = calcular_dv(cuerpo)

    # Agrupar desde la derecha sin alterar el orden de los dígitos.
    grupos = []

    while cuerpo:
        grupos.insert(0, cuerpo[-3:])
        cuerpo = cuerpo[:-3]

    cuerpo_formateado = ".".join(grupos)

    return f"{cuerpo_formateado}-{dv}"


def rut_plano(value) -> str:
    """
    Retorna RUT sin puntos ni guion, incluyendo DV.
    """
    cuerpo, dv = split_rut(value)

    if not cuerpo:
        return ""

    if not dv:
        dv = calcular_dv(cuerpo)

    return f"{cuerpo}{dv}"


def is_valid_rut(value) -> bool:
    """
    Valida RUT chileno.
    """
    cuerpo, dv = split_rut(value)

    if not cuerpo or not dv:
        return False

    return calcular_dv(cuerpo) == dv.upper()
