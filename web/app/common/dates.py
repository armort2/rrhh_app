"""
Helpers oficiales para manejo de fechas en Sistema Grupo CS.
"""

from __future__ import annotations

from datetime import date, datetime
from calendar import monthrange


def parse_date(value, default: date | None = None) -> date | None:
    """
    Convierte valores comunes a date.

    Soporta:
    - date
    - datetime
    - YYYY-MM-DD
    - DD-MM-YYYY
    - DD/MM/YYYY
    """
    if value is None:
        return default

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()

    if not text:
        return default

    formats = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return default


def format_date_cl(value, blank_if_none: bool = True) -> str:
    """
    Formatea una fecha como DD-MM-YYYY.
    """
    d = parse_date(value)

    if d is None:
        return "" if blank_if_none else "Sin fecha"

    return d.strftime("%d-%m-%Y")


def format_date_iso(value, blank_if_none: bool = True) -> str:
    """
    Formatea una fecha como YYYY-MM-DD.
    """
    d = parse_date(value)

    if d is None:
        return "" if blank_if_none else "SIN_FECHA"

    return d.strftime("%Y-%m-%d")


def format_date_long_es(value, blank_if_none: bool = True) -> str:
    """
    Formatea una fecha en español simple.

    Ejemplo:
        2026-05-14 -> "14 de mayo de 2026"
    """
    d = parse_date(value)

    if d is None:
        return "" if blank_if_none else "Sin fecha"

    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


def last_day_of_month(year: int, month: int) -> date:
    """
    Retorna el último día de un mes.
    """
    return date(year, month, monthrange(year, month)[1])


def add_months(value, months: int, keep_last_day: bool = True) -> date | None:
    """
    Suma meses a una fecha.

    Si keep_last_day=True y la fecha original es último día del mes,
    la fecha resultante también será el último día del mes destino.
    """
    d = parse_date(value)

    if d is None:
        return None

    original_last_day = d.day == monthrange(d.year, d.month)[1]

    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1

    target_last_day = monthrange(year, month)[1]

    if keep_last_day and original_last_day:
        day = target_last_day
    else:
        day = min(d.day, target_last_day)

    return date(year, month, day)
