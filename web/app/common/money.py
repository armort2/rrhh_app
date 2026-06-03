"""
Helpers oficiales para manejo de montos en pesos chilenos.

Convenciones:
- Montos internos: int o Decimal.
- Formato visual CLP: $1.234.567
- Parsing tolerante: acepta "$1.234", "1234", "1,234", etc.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


def money_to_decimal(value, default: Decimal | None = Decimal("0")) -> Decimal | None:
    """
    Convierte un valor a Decimal de forma tolerante.

    Ejemplos:
        "$1.234" -> Decimal("1234")
        "1.234,56" -> Decimal("1234.56")
        1234 -> Decimal("1234")
    """
    if value is None:
        return default

    if isinstance(value, Decimal):
        return value

    text = str(value).strip()

    if not text:
        return default

    text = text.replace("$", "").replace(" ", "")

    # Formato chileno/europeo: 1.234,56
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    # Si solo hay coma, asumimos decimal: 1234,56
    elif "," in text:
        text = text.replace(",", ".")
    # Si solo hay puntos, pueden ser separadores de miles: 1.234.567
    elif "." in text:
        parts = text.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            text = "".join(parts)

    text = re.sub(r"[^0-9.\-]", "", text)

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def money_to_int(value, default: int = 0) -> int:
    """
    Convierte un valor monetario a entero, redondeando al peso más cercano.
    """
    amount = money_to_decimal(value, None)

    if amount is None:
        return default

    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_clp(value, blank_if_none: bool = False) -> str:
    """
    Formatea un monto como pesos chilenos.

    Ejemplo:
        1234567 -> "$1.234.567"
    """
    if value is None:
        return "" if blank_if_none else "$0"

    amount = money_to_int(value, 0)
    sign = "-" if amount < 0 else ""
    amount_abs = abs(amount)

    formatted = f"{amount_abs:,}".replace(",", ".")
    return f"{sign}${formatted}"


def format_clp_plain(value, blank_if_none: bool = False) -> str:
    """
    Formatea un monto sin símbolo peso.

    Ejemplo:
        1234567 -> "1.234.567"
    """
    if value is None:
        return "" if blank_if_none else "0"

    amount = money_to_int(value, 0)
    sign = "-" if amount < 0 else ""
    amount_abs = abs(amount)

    return f"{sign}{amount_abs:,}".replace(",", ".")


def is_zero_money(value) -> bool:
    """
    Retorna True si el valor monetario es cero o equivalente.
    """
    return money_to_int(value, 0) == 0
