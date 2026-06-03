# web/app/models/extras_remu.py
from __future__ import annotations

from sqlalchemy.sql import func

from ..extensions import db


class ExtraRemuLote(db.Model):
    __tablename__ = "extras_remu_lotes"

    id = db.Column(db.Integer, primary_key=True)

    # Mantener obra_id: sirve para RBAC por obra, y para facilitar navegación,
    # pero la unicidad del lote debe ser por Centro de Costo + Periodo.
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False, index=True)
    obra = db.relationship("Obra")

    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    centro_costo = db.Column(db.String(100), nullable=False, index=True)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR")
    observaciones = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    items = db.relationship(
        "ExtraRemuItem",
        back_populates="lote",
        lazy=True,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # ✅ Un lote por Centro de Costo y periodo (alineado a la BD)
        db.UniqueConstraint("centro_costo", "anio", "mes", name="uq_extras_remu_lote_cc_periodo"),

        db.CheckConstraint(
            "mes >= 1 AND mes <= 12",
            name="ck_extras_remu_lotes_mes",
        ),

        # ✅ Alineado a BD + app
        db.CheckConstraint(
            "estado IN ('BORRADOR','ENVIADO','APROBADO','CERRADO','EXPORTADO','ANULADO')",
            name="ck_extras_remu_lotes_estado",
        ),
    )

    @property
    def periodo_str(self) -> str:
        return f"{self.anio}-{self.mes:02d}"

    def __repr__(self) -> str:
        return f"<ExtraRemuLote {self.id} {self.anio}-{self.mes:02d} CC={self.centro_costo} obra_id={self.obra_id}>"


class ExtraRemuItem(db.Model):
    __tablename__ = "extras_remu_items"

    id = db.Column(db.Integer, primary_key=True)

    lote_id = db.Column(db.Integer, db.ForeignKey("extras_remu_lotes.id"), nullable=False, index=True)
    lote = db.relationship("ExtraRemuLote", back_populates="items")

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    trabajador = db.relationship("Trabajador")

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)
    contrato = db.relationship("Contrato")

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)
    obra = db.relationship("Obra")

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    empleador = db.relationship("Empleador")

    centro_costo = db.Column(db.String(100), nullable=True)

    concepto_codigo = db.Column(db.String(40), nullable=False)
    concepto_tipo = db.Column(db.String(20), nullable=False)  # BONO / TRATO / JORNADA_EXTRAORDINARIA

    periodo_desde = db.Column(db.Date, nullable=True)
    periodo_hasta = db.Column(db.Date, nullable=True)

    monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    resena = db.Column(db.Text, nullable=False, default="")

    unidades = db.Column(db.Numeric(14, 2), nullable=True)
    valor_unidad = db.Column(db.Numeric(14, 2), nullable=True)

    imponible = db.Column(db.Boolean, nullable=False, default=True)
    tributable = db.Column(db.Boolean, nullable=False, default=True)

    estado = db.Column(
        db.String(20),
        nullable=False,
        default="BORRADOR",
    )  # BORRADOR/APROBADO/ANULADO/EMITIDO_DOCS

    requiere_anexo = db.Column(db.Boolean, nullable=False, default=True)
    estado_doc = db.Column(db.String(30), nullable=False, default="PENDIENTE")

    formato = db.Column(db.String(10), nullable=False, default="AMBOS")  # DOCX/PDF/AMBOS
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # ✅ Alineado con BD (NOT NULL + default now)
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint(
            "concepto_tipo IN ('BONO','TRATO','JORNADA_EXTRAORDINARIA')",
            name="ck_extras_remu_items_tipo",
        ),
        db.CheckConstraint(
            "estado IN ('BORRADOR','APROBADO','ANULADO','EMITIDO_DOCS')",
            name="ck_extras_remu_items_estado",
        ),
        db.CheckConstraint(
            "formato IN ('DOCX','PDF','AMBOS')",
            name="ck_extras_remu_items_formato",
        ),
        db.CheckConstraint(
            "monto >= 0",
            name="ck_extras_remu_items_monto_no_neg",
        ),
        # (Opcional, pero recomendado si ya lo estás usando en routes.py)
        db.CheckConstraint(
            "estado_doc IN ('PENDIENTE','DOCX_GENERADO','PDF_GENERADO','AMBOS_GENERADO')",
            name="ck_extras_remu_items_estado_doc",
        ),
    )

    def __repr__(self) -> str:
        return f"<ExtraRemuItem {self.id} {self.concepto_tipo} {self.concepto_codigo} monto={self.monto}>"