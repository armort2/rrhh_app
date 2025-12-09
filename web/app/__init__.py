# web/app/__init__.py

from flask import Flask

from .config import DevConfig
from .extensions import db


def create_app(config_class=DevConfig):
    app = Flask(__name__)
    
    app.config["SYSTEM_NAME"] = "Sistema Grupo CS"
    app.config["SYSTEM_TAGLINE"] = "Gestión de Recursos Humanos"

    app.config.from_object(config_class)
    db.init_app(app)

    # Blueprints centralizados en app.blueprints
    from .blueprints import (
        core_bp,
        trabajadores_bp,
        contratos_bp,
        obras_bp,
    )
    from .blueprints.documentos import documentos_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(trabajadores_bp)
    app.register_blueprint(contratos_bp)
    app.register_blueprint(obras_bp)
    app.register_blueprint(documentos_bp)

    from .models import Trabajador  # fuerza carga de modelos

    with app.app_context():
        db.create_all()

    # Registrar comandos CLI
    from .cli import register_cli
    register_cli(app)


    return app
