# web/app/models/solicitudes_fondos_nominas_banco.py
from __future__ import annotations

from datetime import date

from sqlalchemy.sql import func

from ..extensions import db


class SolicitudFondosNominaBanco(db.Model):
    __tablename__ = "solicitudes_fondos_nominas_banco"

    id = db.Column(db.Integer, primary_key=True)

    numero = db.Column(db.Integer, nullable=False, unique=True, index=True)

    plantilla = db.Column(db.String(40), nullable=False, default="PAGOS_PROV")
    periodo_anio = db.Column(db.Integer, nullable=False, index=True)
    periodo_mes = db.Column(db.Integer, nullable=False, index=True)

    # QUINCENA / FIN_MES / NULL
    periodo_tipo = db.Column(db.String(20), nullable=True, index=True)

    # TRANSFERENCIA / NOMINA_2 / NULL
    tipo_pago = db.Column(db.String(40), nullable=True, index=True)

    # BORRADOR / GENERADA / PAGADA / ANULADA
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)

    fecha_generacion = db.Column(db.Date, nullable=False, default=date.today)
    observaciones = db.Column(db.Text, nullable=True)

    # Guardamos los filtros usados al preparar la nómina:
    # centros_costos, empresa_ids, estados considerados, etc.
    filtros_json = db.Column(db.JSON, nullable=True)

    total_monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # OJO:
    # Asumo que la tabla real del modelo User es "users".
    # Si en tu sistema es "usuarios", cambia la FK abajo.
    creado_por_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    creado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    creado_por = db.relationship("User", lazy="joined")

    detalles = db.relationship(
        "SolicitudFondosNominaBancoDetalle",
        back_populates="nomina",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SolicitudFondosNominaBancoDetalle.id.asc()",
    )

    __table_args__ = (
        db.CheckConstraint(
            "plantilla IN ('PAGOS_PROV')",
            name="ck_sf_nomina_banco_plantilla",
        ),
        db.CheckConstraint(
            "(periodo_mes >= 1 AND periodo_mes <= 12)",
            name="ck_sf_nomina_banco_periodo_mes",
        ),
        db.CheckConstraint(
            "(periodo_tipo IS NULL OR periodo_tipo IN ('QUINCENA','FIN_MES'))",
            name="ck_sf_nomina_banco_periodo_tipo",
        ),
        db.CheckConstraint(
            "(tipo_pago IS NULL OR tipo_pago IN ('TRANSFERENCIA','NOMINA_2'))",
            name="ck_sf_nomina_banco_tipo_pago",
        ),
        db.CheckConstraint(
            "estado IN ('BORRADOR','GENERADA','PAGADA','ANULADA')",
            name="ck_sf_nomina_banco_estado",
        ),
        db.CheckConstraint(
            "total_monto >= 0",
            name="ck_sf_nomina_banco_total_monto_nonneg",
        ),
    )

    @property
    def periodo_ym(self) -> str:
        return f"{int(self.periodo_anio):04d}-{int(self.periodo_mes):02d}"

    @property
    def estado_label(self) -> str:
        v = (self.estado or "").strip().upper()
        return {
            "BORRADOR": "Borrador",
            "GENERADA": "Generada",
            "PAGADA": "Pagada",
            "ANULADA": "Anulada",
        }.get(v, v.title())

    @property
    def periodo_tipo_label(self) -> str:
        v = (self.periodo_tipo or "").strip().upper()
        return {
            "QUINCENA": "Quincena",
            "FIN_MES": "Fin de mes",
        }.get(v, "Todos")

    @property
    def tipo_pago_label(self) -> str:
        v = (self.tipo_pago or "").strip().upper()
        return {
            "TRANSFERENCIA": "Transferencia",
            "NOMINA_2": "Nómina 2",
        }.get(v, "Todos")

    def __repr__(self) -> str:
        return (
            f"<SolicitudFondosNominaBanco id={self.id} numero={self.numero} "
            f"periodo={self.periodo_ym} estado={self.estado}>"
        )


class SolicitudFondosNominaBancoDetalle(db.Model):
    __tablename__ = "solicitudes_fondos_nominas_banco_detalles"

    id = db.Column(db.Integer, primary_key=True)

    nomina_id = db.Column(
        db.Integer,
        db.ForeignKey("solicitudes_fondos_nominas_banco.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SF_ITEM / RENDICION
    origen_tipo = db.Column(db.String(20), nullable=False, index=True)

    solicitud_id = db.Column(
        db.Integer,
        db.ForeignKey("solicitudes_fondos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    solicitud_item_id = db.Column(
        db.Integer,
        db.ForeignKey("solicitudes_fondos_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # OJO:
    # Aquí NO puse ForeignKey porque no me compartiste el __tablename__
    # exacto de RendicionGasto. Si la tabla real es, por ejemplo,
    # "rendiciones_gastos", podemos cambiar esto luego por FK.
    rendicion_gasto_id = db.Column(
        db.Integer,
        db.ForeignKey("rendiciones_gastos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # REND / TERC / VAR
    seccion = db.Column(db.String(10), nullable=False, index=True)

    # Snapshot histórico del beneficiario al momento de generar la nómina
    rut_beneficiario = db.Column(db.String(20), nullable=True)
    nombre_beneficiario = db.Column(db.String(200), nullable=False)
    codigo_banco = db.Column(db.String(20), nullable=True)
    cuenta_destino = db.Column(db.String(80), nullable=True)
    email_beneficiario = db.Column(db.String(150), nullable=True)

    nro_documento = db.Column(db.String(80), nullable=True)
    glosa = db.Column(db.String(255), nullable=True)
    descripcion = db.Column(db.String(255), nullable=True)

    monto_original = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    monto_pagado_en_esta_nomina = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    creado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    nomina = db.relationship(
        "SolicitudFondosNominaBanco",
        back_populates="detalles",
        lazy="joined",
    )

    solicitud = db.relationship("SolicitudFondos", lazy="joined")
    solicitud_item = db.relationship("SolicitudFondosItem", lazy="joined")
    rendicion_gasto = db.relationship("RendicionGasto", lazy="joined")

    __table_args__ = (
        db.CheckConstraint(
            "origen_tipo IN ('SF_ITEM','RENDICION')",
            name="ck_sf_nomina_banco_det_origen_tipo",
        ),
        db.CheckConstraint(
            "seccion IN ('REND','TERC','VAR')",
            name="ck_sf_nomina_banco_det_seccion",
        ),
        db.CheckConstraint(
            "monto_original >= 0",
            name="ck_sf_nomina_banco_det_monto_original_nonneg",
        ),
        db.CheckConstraint(
            "monto_pagado_en_esta_nomina > 0",
            name="ck_sf_nomina_banco_det_monto_pagado_pos",
        ),
        db.CheckConstraint(
            "monto_pagado_en_esta_nomina <= monto_original",
            name="ck_sf_nomina_banco_det_monto_pagado_le_original",
        ),
        db.CheckConstraint(
            """
            (
                (origen_tipo = 'SF_ITEM' AND solicitud_item_id IS NOT NULL)
                OR
                (origen_tipo = 'RENDICION' AND rendicion_gasto_id IS NOT NULL)
            )
            """,
            name="ck_sf_nomina_banco_det_origen_ref",
        ),
    )

    @property
    def pendiente_despues_de_esta_nomina(self):
        try:
            return (self.monto_original or 0) - (self.monto_pagado_en_esta_nomina or 0)
        except Exception:
            return 0

    @property
    def origen_label(self) -> str:
        v = (self.origen_tipo or "").strip().upper()
        return {
            "SF_ITEM": "Ítem SF",
            "RENDICION": "Rendición",
        }.get(v, v.title())

    def __repr__(self) -> str:
        return (
            f"<SolicitudFondosNominaBancoDetalle id={self.id} nomina_id={self.nomina_id} "
            f"origen={self.origen_tipo} seccion={self.seccion} "
            f"monto={self.monto_pagado_en_esta_nomina}>"
        )