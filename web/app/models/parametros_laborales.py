# web/app/models/parametros_laborales.py
from __future__ import annotations

from ..extensions import db


class ParametroLaboral(db.Model):
    __tablename__ = "parametros_laborales"

    id = db.Column(db.Integer, primary_key=True)

    # Período / vigencia
    periodo = db.Column(db.String(7), nullable=False, unique=True, index=True)  # YYYY-MM
    fecha_vigencia_desde = db.Column(db.Date, nullable=False, index=True)
    fecha_vigencia_hasta = db.Column(db.Date, nullable=False, index=True)

    # Indicadores económicos
    uf = db.Column(db.Numeric(12, 4), nullable=True)
    utm = db.Column(db.Numeric(12, 2), nullable=True)
    uta = db.Column(db.Numeric(12, 2), nullable=True)

    # Rentas mínimas
    renta_minima_dependiente = db.Column(db.Numeric(12, 2), nullable=True)
    renta_minima_menor_mayor65 = db.Column(db.Numeric(12, 2), nullable=True)
    renta_minima_no_remuneracional = db.Column(db.Numeric(12, 2), nullable=True)

    # Topes imponibles
    tope_imponible_afp = db.Column(db.Numeric(12, 2), nullable=True)
    tope_imponible_inp = db.Column(db.Numeric(12, 2), nullable=True)
    tope_imponible_seguro_cesantia = db.Column(db.Numeric(12, 2), nullable=True)

    # Parámetros para gratificación / cálculos laborales
    gratificacion_25_por_ciento_tope_mensual = db.Column(db.Numeric(12, 2), nullable=True)
    sueldo_minimo_para_gratificacion = db.Column(db.Numeric(12, 2), nullable=True)

    # Auditoría / trazabilidad
    fuente = db.Column(db.String(50), nullable=True, index=True)  # PREVIRED / MANUAL / OTRO
    fuente_documento = db.Column(db.String(255), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint(
            r"periodo ~ '^\d{4}-\d{2}$'",
            name="ck_parametros_laborales_periodo",
        ),
        db.CheckConstraint(
            "fecha_vigencia_hasta >= fecha_vigencia_desde",
            name="ck_parametros_laborales_vigencia",
        ),
    )

    def __repr__(self) -> str:
        return f"<ParametroLaboral id={self.id} periodo={self.periodo} fuente={self.fuente}>"