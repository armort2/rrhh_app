# web/app/models/pago_proveedores.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from ..extensions import db
from sqlalchemy import func


class PagoProveedoresLote(db.Model):
    __tablename__ = "pago_proveedores_lotes"

    id = db.Column(db.Integer, primary_key=True)

    pagador = db.Column(db.String(80), nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    archivo_origen = db.Column(db.String(255), nullable=False)
    creado_por_id = db.Column(db.Integer, nullable=True)
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    total_items = db.Column(db.Integer, nullable=False, default=0)
    total_monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    excluidos = db.Column(JSONB, nullable=False, default=list)
    archivo_generado = db.Column(db.String(255), nullable=True)

    items = db.relationship("PagoProveedoresItem", back_populates="lote", cascade="all, delete-orphan")

    estado = db.Column(db.String(20), nullable=False, default="ACTIVO")
    anulado_en = db.Column(db.DateTime(timezone=True), nullable=True)
    anulado_por_id = db.Column(db.Integer, nullable=True)
    anulado_motivo = db.Column(db.String(300), nullable=True)

    estado_pago = db.Column(db.String(20), nullable=False, default="PENDIENTE")  # PENDIENTE | PAGADO
    fecha_pago = db.Column(db.Date, nullable=True)
    pagado_en = db.Column(db.DateTime(timezone=True), nullable=True)
    pagado_por_id = db.Column(db.Integer, nullable=True)
    obs_pago = db.Column(db.String(400), nullable=True)


class PagoProveedoresItem(db.Model):
    __tablename__ = "pago_proveedores_items"

    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey("pago_proveedores_lotes.id", ondelete="CASCADE"), nullable=False)

    tercero_id = db.Column(db.Integer, db.ForeignKey("terceros.id"), nullable=True)
    rut_tercero = db.Column(db.String(20), nullable=False)
    rut_beneficiario = db.Column(db.String(20), nullable=False)

    nombre_beneficiario = db.Column(db.String(255), nullable=False)
    codigo_banco = db.Column(db.String(20), nullable=False)
    cuenta_destino = db.Column(db.String(80), nullable=False)
    correo = db.Column(db.String(150), nullable=False)

    facturas = db.Column(JSONB, nullable=False, default=list)
    monto_total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    glosa = db.Column(db.String(400), nullable=False, default="")

    fila_orden = db.Column(db.Integer, nullable=False, default=1)
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    lote = db.relationship("PagoProveedoresLote", back_populates="items")