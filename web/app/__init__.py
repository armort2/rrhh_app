# web/app/__init__.py
from __future__ import annotations

from flask import Flask, redirect, request, url_for, render_template
from flask_login import current_user

from .config import DevConfig
from .extensions import db, login_manager

# Flask-Migrate (si está instalado y declarado en extensions.py)
try:
    from .extensions import migrate  # type: ignore
except Exception:  # pragma: no cover
    migrate = None  # fallback seguro


def create_app(config_class=DevConfig):
    app = Flask(__name__)

    app.config["SYSTEM_NAME"] = "Sistema Grupo CS"
    app.config["SYSTEM_TAGLINE"] = "Gestión de Recursos Humanos"
    app.config.from_object(config_class)

    # ---------------------------
    # Extensiones
    # ---------------------------
    db.init_app(app)
    login_manager.init_app(app)

    if migrate is not None:
        migrate.init_app(app, db)

    # ---------------------------
    # Blueprints (imports locales para evitar circulares)
    # ---------------------------
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
    )
    from .blueprints.documentos import bp as documentos_bp
    from .blueprints.desvinculaciones.routes import bp as desvinculaciones_bp
    from .blueprints.horarios import bp as horarios_bp
    from .blueprints.inasistencias import bp as inasistencias_bp
    from .blueprints.anticipos.routes import bp as anticipos_bp
    from .blueprints.horas_extras.routes import bp as horas_extras_bp
    from .blueprints.terceros import bp as terceros_bp
    from .blueprints.solicitudes_fondos import bp as solicitudes_fondos_bp

    # Registro
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
    # Login requerido (global)
    # ---------------------------
    @app.before_request
    def require_login():
        from flask_login import current_user  # import local (más robusto)

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

    # ---------------------------
    # Filtros Jinja: RUT
    # ---------------------------
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
            from .extensions import db
            db.session.rollback()
        except Exception:
            pass

        return (
            render_template(
                "errors/500.html",
                user=current_user if current_user.is_authenticated else None,
            ),
            500,
        )
    
    from .utils import format_rut_with_dots

    @app.template_filter("rut_tercero")
    def rut_tercero_filter(t):
        if not t:
            return ""
        rut_digits = getattr(t, "rut_num", None)
        dv = getattr(t, "dv", None)
        return format_rut_with_dots(rut_digits, dv)

    return app