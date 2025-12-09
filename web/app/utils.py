# web/app/utils.py

from datetime import datetime
from decimal import Decimal, InvalidOperation


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
