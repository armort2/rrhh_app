# web/app/services/system_health.py
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import text

from ..extensions import db


@dataclass(frozen=True)
class HealthCheck:
    nombre: str
    estado: str
    detalle: str
    severidad: str = "ok"


def _ok(nombre: str, detalle: str) -> HealthCheck:
    return HealthCheck(nombre=nombre, estado="OK", detalle=detalle, severidad="ok")


def _warn(nombre: str, detalle: str) -> HealthCheck:
    return HealthCheck(nombre=nombre, estado="Revisar", detalle=detalle, severidad="warning")


def _error(nombre: str, detalle: str) -> HealthCheck:
    return HealthCheck(nombre=nombre, estado="Error", detalle=detalle, severidad="danger")


def _disk_check(path: Path) -> HealthCheck:
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        free_pct = (usage.free / usage.total) * 100 if usage.total else 0
        detalle = f"{free_gb:.1f} GB libres de {total_gb:.1f} GB ({free_pct:.0f}% disponible)."
        if free_pct < 10:
            return _error("Espacio en disco", detalle)
        if free_pct < 20:
            return _warn("Espacio en disco", detalle)
        return _ok("Espacio en disco", detalle)
    except Exception as exc:
        return _error("Espacio en disco", f"No fue posible leer el uso de disco: {exc}")


def _db_check() -> HealthCheck:
    try:
        db.session.execute(text("SELECT 1"))
        return _ok("Base de datos", "Conexión activa y consulta básica ejecutada correctamente.")
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        return _error("Base de datos", f"No fue posible ejecutar SELECT 1: {exc}")


def _env_check() -> HealthCheck:
    required = ["DATABASE_URL", "SECRET_KEY"]
    missing = [name for name in required if not os.environ.get(name)]

    if missing:
        return _error("Variables críticas", "Faltan: " + ", ".join(missing))

    optional = ["NEXTCLOUD_ROOT", "NEXTCLOUD_MOUNT_ROOT", "NEXTCLOUD_DOC_ROOT"]
    defined_optional = [name for name in optional if os.environ.get(name)]
    detalle = "Variables críticas presentes."
    if defined_optional:
        detalle += " Nextcloud configurado: " + ", ".join(defined_optional) + "."
    else:
        detalle += " Sin variables opcionales de Nextcloud detectadas."
    return _ok("Variables críticas", detalle)


def _nextcloud_mount_check() -> HealthCheck:
    root = os.environ.get("NEXTCLOUD_MOUNT_ROOT") or os.environ.get("NEXTCLOUD_ROOT")
    if not root:
        return _warn("Montaje Nextcloud", "No hay NEXTCLOUD_MOUNT_ROOT/NEXTCLOUD_ROOT definido en el entorno.")

    path = Path(root)
    if path.exists() and path.is_dir():
        return _ok("Montaje Nextcloud", f"Ruta disponible: {path}")
    return _warn("Montaje Nextcloud", f"Ruta no encontrada o no montada: {path}")


def _version_check() -> HealthCheck:
    version = current_app.config.get("SYSTEM_VERSION", "Sin versión definida")
    return _ok("Versión del sistema", str(version))


def build_system_health() -> dict[str, Any]:
    app_root = Path(current_app.root_path)
    project_root = app_root.parent.parent

    checks = [
        _version_check(),
        _db_check(),
        _env_check(),
        _disk_check(project_root),
        _nextcloud_mount_check(),
    ]

    total = len(checks)
    errors = sum(1 for check in checks if check.severidad == "danger")
    warnings = sum(1 for check in checks if check.severidad == "warning")

    if errors:
        status = "danger"
        resumen = f"{errors} revisión crítica pendiente."
    elif warnings:
        status = "warning"
        resumen = f"{warnings} advertencia(s) detectada(s)."
    else:
        status = "ok"
        resumen = "Todos los controles básicos se encuentran operativos."

    return {
        "checks": checks,
        "total": total,
        "errors": errors,
        "warnings": warnings,
        "status": status,
        "resumen": resumen,
    }
