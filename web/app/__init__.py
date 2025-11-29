import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Configuración básica
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # Registrar rutas
    from .routes import main_bp
    app.register_blueprint(main_bp)

    # Crear tablas (por ahora, solo un ejemplo mínimo)
    from .models import Trabajador
    with app.app_context():
        db.create_all()

    return app
