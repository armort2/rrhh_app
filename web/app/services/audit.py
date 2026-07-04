# web/app/services/audit.py
from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from flask import g, request
from flask_login import current_user
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import AuditLog


SECTION_LABELS = {
    "core": "Inicio / Maestros",
    "trabajadores": "Trabajadores",
    "contratos": "Contratos",
    "contratos_vencimientos": "Contratos por vencer",
    "anexos": "Anexos plazo fijo",
    "anexos_indefinidos": "Anexos indefinidos",
    "anexos_cambio_sueldo": "Anexos cambio sueldo",
    "anexos_cambio_cargo": "Anexos cambio cargo",
    "anexos_masivos": "Anexos masivos",
    "desvinculaciones": "Desvinculaciones",
    "documentos": "Documentos",
    "certificados": "Certificados",
    "vacaciones": "Vacaciones",
    "inasistencias": "Inasistencias",
    "horas_extras": "Horas extras",
    "anticipos": "Anticipos",
    "sueldos": "Sueldos",
    "extras_remuneracion": "Bonos, tratos y extras",
    "solicitudes_fondos": "Solicitudes de fondos",
    "rendiciones_gastos": "Rendiciones de gastos",
    "transferencias_bancarias": "Transferencias bancarias",
    "pago_proveedores": "Pago a proveedores",
    "egresos": "Egresos",
    "acuerdos_pago": "Acuerdos de pago",
    "prevencion_riesgos": "Prevención de riesgos",
    "dashboard": "Dashboard",
    "reporteria": "Reportería",
    "obras": "Obras",
    "terceros": "Terceros",
    "horarios": "Horarios",
    "feriados": "Feriados",
    "parametros_laborales": "Parámetros laborales",
    "cumplimiento_laboral": "Cumplimiento laboral",
    "admin": "Administración",
    "auth": "Autenticación",
}

_SKIP_PATH_PREFIXES = (
    "/static/",
    "/favicon.ico",
)

_SKIP_EXTENSIONS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".map",
)


def mark_audit_start() -> None:
    """Marca inicio de request para calcular duración en after_request."""
    g.audit_started_at = perf_counter()


def _audit_table_exists() -> bool:
    """Evita romper la app si todavía no se ejecutó la migración."""
    try:
        return inspect(db.engine).has_table("audit_logs")
    except Exception:
        return False


def should_audit_request() -> bool:
    path = request.path or ""
    if request.method == "OPTIONS":
        return False
    if path.startswith(_SKIP_PATH_PREFIXES):
        return False
    if path.lower().endswith(_SKIP_EXTENSIONS):
        return False
    if not getattr(current_user, "is_authenticated", False):
        return False
    return True


def get_client_ip() -> str | None:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or request.headers.get("X-Real-IP") or request.remote_addr


def resolve_section(blueprint: str | None, endpoint: str | None, path: str | None) -> str:
    bp = (blueprint or "").strip()
    if bp in SECTION_LABELS:
        return SECTION_LABELS[bp]

    ep = endpoint or ""
    if "." in ep:
        first = ep.split(".", 1)[0]
        if first in SECTION_LABELS:
            return SECTION_LABELS[first]

    path = path or ""
    if path.startswith("/cargos"):
        return "Cargos"
    if path == "/" or path.startswith("/index"):
        return "Inicio"
    return "General"


def resolve_action(endpoint: str | None, method: str | None, path: str | None) -> str:
    method = (method or "").upper()
    endpoint = endpoint or ""
    action_name = endpoint.split(".", 1)[1] if "." in endpoint else endpoint
    action_name = action_name.replace("_", " ").strip() or (path or "")
    if method == "GET":
        return f"Ver {action_name}".strip()
    if method == "POST":
        return f"Enviar/guardar {action_name}".strip()
    return f"{method} {action_name}".strip()


def _safe_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    txt = str(value)
    if len(txt) > limit:
        return txt[: limit - 3] + "..."
    return txt


def write_audit_log(
    *,
    user: Any | None = None,
    event_type: str = "request",
    section: str | None = None,
    action: str | None = None,
    method: str | None = None,
    path: str | None = None,
    endpoint: str | None = None,
    blueprint: str | None = None,
    status_code: int | None = None,
    response_ms: int | None = None,
) -> None:
    if not _audit_table_exists():
        return

    user = user if user is not None else current_user
    try:
        user_id = int(user.get_id()) if getattr(user, "is_authenticated", False) and user.get_id() else None
    except Exception:
        user_id = None

    try:
        row = AuditLog(
            user_id=user_id,
            username=_safe_text(getattr(user, "username", None), 80),
            nombre=_safe_text(getattr(user, "nombre", None), 120),
            event_type=_safe_text(event_type, 40) or "request",
            section=_safe_text(section or resolve_section(blueprint, endpoint, path), 80),
            action=_safe_text(action or resolve_action(endpoint, method, path), 120),
            method=_safe_text(method or request.method, 10),
            path=_safe_text(path or request.full_path.rstrip("?"), 500),
            endpoint=_safe_text(endpoint or request.endpoint, 160),
            blueprint=_safe_text(blueprint or request.blueprint, 80),
            status_code=status_code,
            response_ms=response_ms,
            ip_address=_safe_text(get_client_ip(), 80),
            user_agent=_safe_text(request.headers.get("User-Agent"), 500),
            referrer=_safe_text(request.referrer, 500),
            created_at=datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def audit_after_request(response):
    if not should_audit_request():
        return response

    started = getattr(g, "audit_started_at", None)
    response_ms = None
    if started is not None:
        response_ms = int((perf_counter() - started) * 1000)

    write_audit_log(
        event_type="request",
        method=request.method,
        path=request.full_path.rstrip("?"),
        endpoint=request.endpoint,
        blueprint=request.blueprint,
        status_code=response.status_code,
        response_ms=response_ms,
    )
    return response


def audit_event(event_type: str, action: str, user: Any | None = None) -> None:
    """Registra eventos manuales, como login/logout."""
    write_audit_log(
        user=user,
        event_type=event_type,
        section="Autenticación",
        action=action,
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        blueprint=request.blueprint,
        status_code=None,
        response_ms=None,
    )


def audit_business_event(
    *,
    section: str,
    action: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    user: Any | None = None,
) -> None:
    """Registra una acción de negocio relevante en la bitácora existente.

    No requiere migraciones: usa `audit_logs.event_type = "business"` y
    concentra la trazabilidad funcional en `section` + `action`.

    Recomendación operativa: llamarlo después del commit de la transacción
    principal, porque `write_audit_log` abre y confirma su propio registro.
    """
    entity_txt = ""
    if entity_type and entity_id is not None:
        entity_txt = f" · {entity_type} #{entity_id}"

    write_audit_log(
        user=user,
        event_type="business",
        section=section,
        action=f"{action}{entity_txt}",
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        blueprint=request.blueprint,
        status_code=None,
        response_ms=None,
    )
