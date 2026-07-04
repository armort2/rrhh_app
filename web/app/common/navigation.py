"""
Helpers de navegación segura.

Centraliza la validación de parámetros `next` / `next_url` para evitar
redirecciones abiertas y mantener una regla única entre blueprints.
"""

from __future__ import annotations

from urllib.parse import urlparse, urljoin

from flask import request


def is_safe_redirect_target(target: str | None) -> bool:
    """Retorna True solo si `target` apunta al mismo host o a una ruta interna.

    Acepta:
    - /trabajadores/1
    - /contratos/?estado=VIGENTE
    - URL absoluta del mismo host

    Rechaza:
    - https://dominio-externo.cl/...
    - //dominio-externo.cl/...
    - javascript:...
    """
    target = (target or "").strip()
    if not target:
        return False

    if any(ch in target for ch in ("\r", "\n", "\t")):
        return False

    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))

    if test_url.scheme not in {"http", "https"}:
        return False

    return (test_url.scheme, test_url.netloc) == (ref_url.scheme, ref_url.netloc)


def safe_next_url(target: str | None, fallback: str | None = None) -> str | None:
    """Devuelve una URL segura para redirect o un fallback interno.

    El fallback puede venir ya generado con `url_for`. Si no hay destino seguro
    ni fallback válido, retorna None para que la ruta decida su destino natural.
    """
    target = (target or "").strip()
    if target and is_safe_redirect_target(target):
        return target

    fallback = (fallback or "").strip()
    if fallback and is_safe_redirect_target(fallback):
        return fallback

    return None


def safe_next_from_request(*, fallback: str | None = None, keys: tuple[str, ...] = ("next", "next_url")) -> str | None:
    """Busca un destino `next` en args/form y lo normaliza con `safe_next_url`."""
    for key in keys:
        value = request.args.get(key) or request.form.get(key)
        if value:
            safe = safe_next_url(value, fallback=None)
            if safe:
                return safe
    return safe_next_url(None, fallback=fallback) if fallback else None
