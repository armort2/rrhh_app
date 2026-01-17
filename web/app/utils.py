# web/app/utils.py

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import re


def parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_int(value: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_decimal(value: str):
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None

def format_rut_parts(rut_digits: str | None, dv: str | None) -> str:
    """
    Formatea rut (cuerpo) + dv a 12.345.678-9
    """
    if not rut_digits or not dv:
        return ""
    digits = re.sub(r"\D", "", str(rut_digits))
    dv = str(dv).strip().upper()

    if not digits or dv not in "0123456789K":
        return ""

    rev = digits[::-1]
    chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    with_dots = ".".join(c[::-1] for c in chunks[::-1])
    return f"{with_dots}-{dv}"

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

def fecha_larga_es(fecha: date | None) -> str:
    if not fecha:
        return ""
    return f"{fecha.day} de {MESES_ES[fecha.month]} de {fecha.year}"