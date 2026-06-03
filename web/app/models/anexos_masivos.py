from __future__ import annotations

from ..extensions import db


class ProcesoAnexoMasivo(db.Model):
    __tablename__ = "procesos_anexos_masivos"

    id = db.Column(db.Integer, primary_key=True)

    # SUELDO_MINIMO / AUMENTO_SUELDO / etc.
    tipo_proceso = db.Column(db.String(30), nullable=False, index=True)

    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)

    fecha_anexo = db.Column(db.Date, nullable=False, index=True)
    fecha_vigencia = db.Column(db.Date, nullable=False, index=True)

    parametro_laboral_id = db.Column(
        db.Integer,
        db.ForeignKey("parametros_laborales.id"),
        nullable=True,
        index=True,
    )

    sueldo_base_objetivo = db.Column(db.Numeric(12, 2), nullable=False)

    filtrar_solo_vigentes = db.Column(db.Boolean, nullable=False, default=True)
    horas_semanales_minimas = db.Column(db.Integer, nullable=False, default=40)
    solo_sueldos_inferiores_objetivo = db.Column(db.Boolean, nullable=False, default=True)

    # Datos legales / documentales del reajuste
    ley_s_minimo_nro = db.Column(db.String(50), nullable=True)
    ley_s_minimo_fecha_publicacion = db.Column(db.Date, nullable=True)

    usar_articulo_tercero = db.Column(db.Boolean, nullable=False, default=False)
    articulo_tercero_texto = db.Column(db.Text, nullable=True)

    formato_generacion = db.Column(db.String(10), nullable=False, default="AMBOS")

    # BORRADOR / GENERADO / APLICADO / CERRADO / ANULADO
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)

    observaciones = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    detalles = db.relationship(
        "DetalleAnexoMasivo",
        back_populates="proceso",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="DetalleAnexoMasivo.id.asc()",
    )

    @property
    def total_detalles(self) -> int:
        return len(self.detalles or [])

    @property
    def total_seleccionados(self) -> int:
        return sum(1 for d in (self.detalles or []) if d.seleccionado)

    @property
    def total_generados(self) -> int:
        return sum(1 for d in (self.detalles or []) if d.estado == "GENERADO")

    @property
    def total_aplicados(self) -> int:
        return sum(1 for d in (self.detalles or []) if d.estado == "APLICADO")

    def __repr__(self) -> str:
        return f"<ProcesoAnexoMasivo id={self.id} tipo={self.tipo_proceso} estado={self.estado}>"


class DetalleAnexoMasivo(db.Model):
    __tablename__ = "detalles_anexos_masivos"

    id = db.Column(db.Integer, primary_key=True)

    proceso_id = db.Column(
        db.Integer,
        db.ForeignKey("procesos_anexos_masivos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proceso = db.relationship("ProcesoAnexoMasivo", back_populates="detalles")

    trabajador_id = db.Column(
        db.Integer,
        db.ForeignKey("trabajadores.id"),
        nullable=False,
        index=True,
    )

    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id"),
        nullable=False,
        index=True,
    )

    horas_semanales = db.Column(db.Integer, nullable=True)
    sueldo_base_actual = db.Column(db.Numeric(12, 2), nullable=False)
    sueldo_base_nuevo = db.Column(db.Numeric(12, 2), nullable=False)

    seleccionado = db.Column(db.Boolean, nullable=False, default=True)

    # PENDIENTE / GENERADO / ERROR / APLICADO / OMITIDO
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE", index=True)

    observacion = db.Column(db.Text, nullable=True)

    formato = db.Column(db.String(10), nullable=True)
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.String(500), nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.String(500), nullable=True)

    meta = db.Column(db.JSON, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint(
            "proceso_id",
            "contrato_id",
            name="uq_detalle_anexo_masivo_proceso_contrato",
        ),
    )

    def __repr__(self) -> str:
        return f"<DetalleAnexoMasivo id={self.id} proceso={self.proceso_id} contrato={self.contrato_id}>"