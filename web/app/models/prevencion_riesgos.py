# web/app/models/prevencion_riesgos.py
from __future__ import annotations

from ..extensions import db


class PrevTipoEPP(db.Model):
    __tablename__ = "prev_tipos_epp"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True, index=True)
    descripcion = db.Column(db.Text, nullable=True)

    requiere_talla = db.Column(db.Boolean, nullable=False, default=False)
    requiere_reposicion = db.Column(db.Boolean, nullable=False, default=True)
    dias_reposicion_sugerida = db.Column(db.Integer, nullable=True)

    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PrevTipoEPP id={self.id} nombre={self.nombre!r}>"


class PrevEntregaEPP(db.Model):
    __tablename__ = "prev_entregas_epp"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)

    # Nuevo vínculo contractual.
    # Nullable para no romper registros ya creados antes de esta mejora.
    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False, index=True)

    fecha_entrega = db.Column(db.Date, nullable=False, index=True)
    observacion = db.Column(db.Text, nullable=True)

    documento_nombre = db.Column(db.String(255), nullable=True)
    documento_path = db.Column(db.Text, nullable=True)

    registrado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    trabajador = db.relationship("Trabajador", foreign_keys=[trabajador_id], lazy="joined")
    contrato = db.relationship("Contrato", foreign_keys=[contrato_id], lazy="joined")
    obra = db.relationship("Obra", foreign_keys=[obra_id], lazy="joined")
    registrado_por = db.relationship("User", foreign_keys=[registrado_por_id], lazy="joined")

    items = db.relationship(
        "PrevEntregaEPPItem",
        back_populates="entrega",
        cascade="all, delete-orphan",
        lazy=True,
    )


class PrevEntregaEPPItem(db.Model):
    __tablename__ = "prev_entrega_epp_items"

    id = db.Column(db.Integer, primary_key=True)

    entrega_id = db.Column(
        db.Integer,
        db.ForeignKey("prev_entregas_epp.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo_epp_id = db.Column(db.Integer, db.ForeignKey("prev_tipos_epp.id"), nullable=False, index=True)

    cantidad = db.Column(db.Integer, nullable=False, default=1)
    talla = db.Column(db.String(50), nullable=True)
    marca_modelo = db.Column(db.String(150), nullable=True)
    fecha_reposicion_sugerida = db.Column(db.Date, nullable=True, index=True)
    observacion = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    entrega = db.relationship("PrevEntregaEPP", back_populates="items")
    tipo_epp = db.relationship("PrevTipoEPP", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("cantidad > 0", name="ck_prev_entrega_epp_items_cantidad_pos"),
    )


class PrevCharlaSeguridad(db.Model):
    __tablename__ = "prev_charlas_seguridad"

    id = db.Column(db.Integer, primary_key=True)

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False, index=True)

    titulo = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(50), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)

    relator = db.Column(db.String(150), nullable=True)
    duracion_minutos = db.Column(db.Integer, nullable=True)
    tema = db.Column(db.Text, nullable=True)
    observacion = db.Column(db.Text, nullable=True)

    documento_nombre = db.Column(db.String(255), nullable=True)
    documento_path = db.Column(db.Text, nullable=True)

    registrado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    obra = db.relationship("Obra", foreign_keys=[obra_id], lazy="joined")
    registrado_por = db.relationship("User", foreign_keys=[registrado_por_id], lazy="joined")

    asistentes = db.relationship(
        "PrevCharlaAsistente",
        back_populates="charla",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "duracion_minutos IS NULL OR duracion_minutos > 0",
            name="ck_prev_charlas_duracion_pos",
        ),
    )


class PrevCharlaAsistente(db.Model):
    __tablename__ = "prev_charla_asistentes"

    id = db.Column(db.Integer, primary_key=True)

    charla_id = db.Column(
        db.Integer,
        db.ForeignKey("prev_charlas_seguridad.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)

    # Nuevo vínculo contractual por asistente.
    # La charla sigue siendo un evento de obra; cada asistente queda vinculado a su contrato.
    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    asistio = db.Column(db.Boolean, nullable=False, default=True)
    observacion = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    charla = db.relationship("PrevCharlaSeguridad", back_populates="asistentes")
    trabajador = db.relationship("Trabajador", foreign_keys=[trabajador_id], lazy="joined")
    contrato = db.relationship("Contrato", foreign_keys=[contrato_id], lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("charla_id", "trabajador_id", "contrato_id", name="uq_prev_charla_asistente_contrato"),
    )


class PrevDocumentoPreventivo(db.Model):
    __tablename__ = "prev_documentos_preventivos"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)

    # Nuevo vínculo contractual.
    # Nullable para mantener compatibilidad con registros creados antes de esta mejora.
    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    tipo_documento = db.Column(db.String(80), nullable=False, index=True)
    fecha_emision = db.Column(db.Date, nullable=False, index=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True, index=True)

    estado = db.Column(db.String(20), nullable=False, default="VIGENTE", index=True)

    archivo_nombre = db.Column(db.String(255), nullable=True)
    archivo_path = db.Column(db.Text, nullable=True)
    observacion = db.Column(db.Text, nullable=True)

    registrado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    trabajador = db.relationship("Trabajador", foreign_keys=[trabajador_id], lazy="joined")
    contrato = db.relationship("Contrato", foreign_keys=[contrato_id], lazy="joined")
    obra = db.relationship("Obra", foreign_keys=[obra_id], lazy="joined")
    registrado_por = db.relationship("User", foreign_keys=[registrado_por_id], lazy="joined")

    __table_args__ = (
        db.CheckConstraint(
            "estado IN ('VIGENTE', 'POR_VENCER', 'VENCIDO', 'PENDIENTE', 'ANULADO')",
            name="ck_prev_documentos_estado",
        ),
        db.CheckConstraint(
            "fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_emision",
            name="ck_prev_documentos_vigencia",
        ),
    )
