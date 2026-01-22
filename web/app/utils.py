# web/app/utils.py

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import re
from functools import wraps

from flask import flash, redirect, url_for, request, abort
from flask_login import current_user


# ---------------------------
# Parsers
# ---------------------------
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


# ---------------------------
# Formatos / helpers
# ---------------------------
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


# ---------------------------
# Auth / Permisos (decoradores)
# ---------------------------
def _normalize_roles(*role_names: str) -> set[str]:
    return {str(r).strip().upper() for r in role_names if r is not None and str(r).strip()}


def _user_has_any_role(user, allowed: set[str]) -> bool:
    """
    Usa el método User.has_role() si existe.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    has_role = getattr(user, "has_role", None)
    if callable(has_role):
        return user.has_role(*allowed)
    return False


def active_user_required(message: str = "Tu usuario no está activo."):
    """
    Bloquea acceso si el usuario está inactivo.
    Útil para reforzar seguridad cuando 'is_active' se usa de forma lógica.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("auth.login"))  # ajusta si tu blueprint difiere
            if not getattr(current_user, "is_active", True):
                flash(message, "danger")
                return redirect(url_for("main.index"))  # ajusta si tu home difiere
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def roles_required(*role_names: str, redirect_endpoint: str = "main.index", message: str = "No tienes permisos para realizar esta acción."):
    """
    Permite continuar solo si el usuario posee al menos uno de los roles requeridos.
    """
    allowed = _normalize_roles(*role_names)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("auth.login"))  # ajusta si tu blueprint difiere

            if not _user_has_any_role(current_user, allowed):
                flash(message, "danger")
                return redirect(url_for(redirect_endpoint))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def read_only_for_roles(*role_names: str, redirect_endpoint: str, message: str = "No tienes permisos para modificar este módulo."):
    """
    Bloquea intentos de modificación (POST/PUT/PATCH/DELETE) para roles específicos.
    Útil cuando un módulo debe ser 'solo lectura' para OPERADOR/REVISOR.
    """
    blocked = _normalize_roles(*role_names)
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("auth.login"))  # ajusta si tu blueprint difiere

            if request.method in write_methods and _user_has_any_role(current_user, blocked):
                flash(message, "danger")
                return redirect(url_for(redirect_endpoint))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def format_rut_with_dots(rut_digits, dv) -> str:
    """
    Formatea RUT chileno con puntos y guión.
    Ej: 80565900 + '9' => '80.565.900-9'
    """
    if rut_digits is None:
        rut_str = ""
    else:
        rut_str = str(rut_digits).strip()

    dv_str = (str(dv).strip().upper() if dv is not None else "")

    if not rut_str and not dv_str:
        return ""
    if not rut_str and dv_str:
        return f"-{dv_str}"
    if rut_str and not dv_str:
        return rut_str

    # puntos cada 3 desde la derecha
    parts = []
    while len(rut_str) > 3:
        parts.insert(0, rut_str[-3:])
        rut_str = rut_str[:-3]
    if rut_str:
        parts.insert(0, rut_str)

    return f"{'.'.join(parts)}-{dv_str}"