# web/app/models/audit.py
from __future__ import annotations

from datetime import datetime

from ..extensions import db


class AuditLog(db.Model):
    """Bitácora de navegación y acciones básicas del sistema.

    Registra accesos autenticados a rutas internas y eventos relevantes
    como inicio/cierre de sesión. La finalidad es trazabilidad operativa,
    control de acceso y análisis de uso por módulo.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    # Usuario al momento del evento. Se guarda username/nombre como snapshot
    # para conservar trazabilidad aunque el usuario cambie después.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    username = db.Column(db.String(80), nullable=True, index=True)
    nombre = db.Column(db.String(120), nullable=True)

    event_type = db.Column(db.String(40), nullable=False, default="request", index=True)
    section = db.Column(db.String(80), nullable=True, index=True)
    action = db.Column(db.String(120), nullable=True)

    method = db.Column(db.String(10), nullable=True, index=True)
    path = db.Column(db.String(500), nullable=True, index=True)
    endpoint = db.Column(db.String(160), nullable=True, index=True)
    blueprint = db.Column(db.String(80), nullable=True, index=True)

    status_code = db.Column(db.Integer, nullable=True, index=True)
    response_ms = db.Column(db.Integer, nullable=True)

    ip_address = db.Column(db.String(80), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    referrer = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref=db.backref("audit_logs", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<AuditLog {self.event_type} {self.username} {self.method} {self.path}>"
