# web/app/__init__.py
from __future__ import annotations

from flask import Flask, abort, redirect, request, url_for, render_template
from flask_login import current_user
from datetime import datetime
from pathlib import Path
import os

from .config import DevConfig
from .extensions import db, login_manager
from .services.audit import audit_after_request, mark_audit_start

from .services.rut_format import rut_con_puntos

from zoneinfo import ZoneInfo

# Flask-Migrate (si está instalado y declarado en extensions.py)
try:
    from .extensions import migrate  # type: ignore
except Exception:  # pragma: no cover
    migrate = None  # fallback seguro


def _read_system_version() -> str:
    """Lee la versión institucional del sistema desde VERSION.

    Regla operacional:
    1) SYSTEM_VERSION_OVERRIDE permite forzar una versión puntual.
    2) El archivo VERSION del proyecto tiene prioridad sobre variables genéricas
       del entorno Docker, evitando textos como dev o sin-version en producción.
    3) SYSTEM_VERSION queda solo como respaldo si no existe VERSION.
    """
    forced_version = os.environ.get("SYSTEM_VERSION_OVERRIDE")
    if forced_version and forced_version.strip():
        return forced_version.strip()

    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        version_file = parent / "VERSION"
        try:
            file_version = version_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if file_version:
            return file_version

    env_version = os.environ.get("SYSTEM_VERSION")
    if env_version and env_version.strip() and env_version.strip().lower() not in {"dev", "development"}:
        return env_version.strip()

    return "2026.06.03-v9"

def create_app(config_class=DevConfig):
    app = Flask(__name__)

    app.config.from_object(config_class)
    app.config["SYSTEM_NAME"] = "Sistema Grupo CS"
    app.config["SYSTEM_TAGLINE"] = "Gestión de Recursos Humanos"
    app.config["SYSTEM_VERSION"] = _read_system_version()

    # ---------------------------
    # Extensiones
    # ---------------------------
    db.init_app(app)
    login_manager.init_app(app)

    if migrate is not None:
        migrate.init_app(app, db)

    @app.context_processor
    def _inject_now():
        return {"now": datetime.now}

    # ---------------------------
    # Blueprints (imports locales para evitar circulares)
    # ---------------------------
    # OJO: Este import viene desde app/blueprints/__init__.py
    from .blueprints import (
        core_bp,
        trabajadores_bp,
        contratos_bp,
        obras_bp,
        admin_bp,
        anexos_bp,
        anexos_indefinidos_bp,
        terceros_bp,
        solicitudes_fondos_bp,
        rendiciones_gastos_bp,
        # ✅ NO importar acá egresos/acuerdos/transferencias si no están expuestos en blueprints/__init__.py
    )

    # Blueprints que se importan directo (porque no necesariamente están expuestos en app/blueprints/__init__.py)
    from .blueprints.documentos import bp as documentos_bp
    from .blueprints.desvinculaciones.routes import bp as desvinculaciones_bp
    from .blueprints.horarios import bp as horarios_bp
    from .blueprints.inasistencias import bp as inasistencias_bp
    from .blueprints.anticipos.routes import bp as anticipos_bp
    from .blueprints.horas_extras.routes import bp as horas_extras_bp
    from .blueprints.certificados import bp as certificados_bp
    from .blueprints.sueldos.routes import bp as sueldos_bp

    from .blueprints.egresos import bp as egresos_bp
    from .blueprints.acuerdos_pago import bp as acuerdos_pago_bp
    from .blueprints.transferencias_bancarias import bp as transferencias_bancarias_bp
    from .blueprints.vacaciones import bp as vacaciones_bp
    from .blueprints.feriados import bp as feriados_bp
    from .blueprints.pago_proveedores import bp as pago_proveedores_bp
    from .blueprints.extras_remuneracion import bp as extras_remuneracion_bp
    from .blueprints.contratos_vencimientos import bp as contratos_vencimientos_bp
    from .blueprints.dashboard import bp as dashboard_bp
    from .blueprints.parametros_laborales import bp as parametros_laborales_bp
    from .blueprints.anexos_masivos import bp as anexos_masivos_bp
    from .blueprints.anexos_cambio_sueldo import bp as anexos_cambio_sueldo_bp
    from .blueprints.anexos_cambio_cargo import bp as anexos_cambio_cargo_bp
    from .blueprints.prevencion_riesgos import bp as prevencion_riesgos_bp
    from .blueprints.reporteria import bp as reporteria_bp
    from .blueprints.cumplimiento_laboral import bp as cumplimiento_laboral_bp
    from .blueprints.gestion_rrhh import bp as gestion_rrhh_bp


    # ---------------------------
    # Registro de blueprints
    # ---------------------------
    app.register_blueprint(horarios_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(trabajadores_bp)
    app.register_blueprint(contratos_bp)
    app.register_blueprint(obras_bp)
    app.register_blueprint(documentos_bp)
    app.register_blueprint(anexos_bp)
    app.register_blueprint(anexos_indefinidos_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(desvinculaciones_bp)
    app.register_blueprint(inasistencias_bp)
    app.register_blueprint(anticipos_bp)
    app.register_blueprint(horas_extras_bp)
    app.register_blueprint(terceros_bp)
    app.register_blueprint(solicitudes_fondos_bp)
    app.register_blueprint(rendiciones_gastos_bp)
    app.register_blueprint(certificados_bp)
    app.register_blueprint(sueldos_bp)
    app.register_blueprint(egresos_bp)
    app.register_blueprint(acuerdos_pago_bp)
    app.register_blueprint(transferencias_bancarias_bp)
    app.register_blueprint(vacaciones_bp)
    app.register_blueprint(feriados_bp)
    app.register_blueprint(pago_proveedores_bp)
    app.register_blueprint(extras_remuneracion_bp)
    app.register_blueprint(contratos_vencimientos_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(parametros_laborales_bp)
    app.register_blueprint(anexos_masivos_bp)
    app.register_blueprint(anexos_cambio_sueldo_bp)
    app.register_blueprint(anexos_cambio_cargo_bp)
    app.register_blueprint(prevencion_riesgos_bp)
    app.register_blueprint(reporteria_bp)
    app.register_blueprint(cumplimiento_laboral_bp)
    app.register_blueprint(gestion_rrhh_bp)
    
    # Auth blueprint
    from .auth import auth as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # ---------------------------
    # User loader
    # ---------------------------
    from .models import User  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # ---------------------------
    # Auditoría / Bitácora
    # ---------------------------
    @app.before_request
    def audit_start():
        mark_audit_start()
        return None

    @app.after_request
    def audit_request(response):
        return audit_after_request(response)

    # ---------------------------
    # Login requerido (global)
    # ---------------------------
    @app.before_request
    def require_login():
        path = request.path

        # Permitir estáticos
        if path.startswith("/static/"):
            return None

        # Permitir login/logout
        if path.startswith("/auth/login") or path.startswith("/auth/logout"):
            return None

        # Forzar autenticación
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=path))

        return None

    @app.before_request
    def require_module_permission():
        """Barrera RBAC V9 por módulo.

        El navbar ya oculta accesos según permisos, pero esta capa evita que un
        usuario entre manualmente escribiendo una URL directa.
        """
        path = request.path or ""

        if path.startswith("/static/"):
            return None
        if path.startswith("/auth/login") or path.startswith("/auth/logout"):
            return None
        if not current_user.is_authenticated:
            return None

        from .services.access_control import user_can_access_request

        if not user_can_access_request(current_user, request.blueprint, request.endpoint, request.method):
            abort(403)

        return None

    # ---------------------------
    # Filtros Jinja: RUT
    # ---------------------------

    app.jinja_env.filters["rut"] = rut_con_puntos  # filtro genérico de RUT con puntos (siempre disponible)

    from .utils import format_rut_parts  # una sola fuente


    @app.template_filter("rut_trabajador")
    def rut_trabajador_filter(t):
        if not t:
            return ""
        rut_digits = getattr(t, "rut", None)
        dv = getattr(t, "dv", None)
        return format_rut_parts(rut_digits, dv) or (str(rut_digits) if rut_digits else "")

    @app.template_filter("rut_any")
    def rut_any_filter(obj, rut_attr: str = "rut", dv_attr: str = "dv"):
        """
        Formatea RUT para cualquier objeto:
        - Trabajador: rut + dv
        - Tercero: rut_num + dv
        - También permite especificar attrs custom.
        """
        if not obj:
            return ""
        rut_digits = getattr(obj, rut_attr, None)
        dv = getattr(obj, dv_attr, None)
        return format_rut_parts(rut_digits, dv) or (str(rut_digits) if rut_digits else "")

    from .utils import format_rut_with_dots

    @app.template_filter("rut_tercero")
    def rut_tercero_filter(t):
        if not t:
            return ""
        rut_digits = getattr(t, "rut_num", None)
        dv = getattr(t, "dv", None)
        return format_rut_with_dots(rut_digits, dv)
    
    CL_TZ = ZoneInfo("America/Santiago")

    @app.template_filter("dt_cl")
    def dt_cl_filter(value, fmt: str = "%d-%m-%Y %H:%M"):
        """
        Convierte un datetime a hora Chile (America/Santiago) y formatea.
        - Si viene naive, se asume UTC (comportamiento típico cuando guardan UTC en DB).
        - Si viene aware, se convierte a CL.
        """
        if not value:
            return ""
        dt = value

        # si viene naive, asumimos UTC
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        dt = dt.astimezone(CL_TZ)
        return dt.strftime(fmt)

    # ---------------------------
    # CLI (un solo punto de registro)
    # ---------------------------
    from .cli import register_cli
    register_cli(app)

    # ---------------------------
    # Handlers de errores
    # ---------------------------
    @app.errorhandler(403)
    def forbidden(error):
        return (
            render_template(
                "errors/403.html",
                user=current_user if current_user.is_authenticated else None,
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template(
                "errors/404.html",
                user=current_user if current_user.is_authenticated else None,
            ),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        # IMPORTANTE: rollback defensivo
        try:
            from .extensions import db as _db
            _db.session.rollback()
        except Exception:
            pass

        return (
            render_template(
                "errors/500.html",
                user=current_user if current_user.is_authenticated else None,
            ),
            500,
        )

    # ---------------------------
    # Context processors
    # ---------------------------

    @app.context_processor
    def _inject_access_control():
        from .services.access_control import (
            get_role_definitions,
            user_can,
            user_has_any_permission,
            user_permissions,
        )
        return {
            "current_user_can": lambda permission: user_can(current_user, permission),
            "current_user_has_any_permission": lambda *permissions: user_has_any_permission(current_user, *permissions),
            "current_user_permissions": lambda: user_permissions(current_user),
            "system_role_definitions": get_role_definitions,
        }

    @app.context_processor
    def _inject_config():
        """Inyecta `config` en el contexto de Jinja para plantillas que lo esperan."""
        return {"config": app.config}


    # ---------------------------
    # Números en formato chileno (con puntos)
    # ---------------------------
    def fmt_cl(value, decimals=0):
        """
        Formato numérico chileno:
        miles con punto, decimal con coma.
        """
        if value is None:
            return ""

        try:
            n = float(value)

            if decimals == 0:
                s = f"{n:,.0f}"
            else:
                s = f"{n:,.{decimals}f}"

            return s.replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return value

    app.jinja_env.filters["fmt_cl"] = fmt_cl

    return app