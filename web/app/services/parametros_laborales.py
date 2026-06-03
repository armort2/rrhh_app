# web/app/services/parametros_laborales.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from ..models import ParametroLaboral


def periodo_from_date(fecha: date | datetime | None) -> str:
    """
    Convierte una fecha a período YYYY-MM.
    Si no viene fecha, devuelve "".
    """
    if not fecha:
        return ""
    return f"{fecha.year:04d}-{fecha.month:02d}"


def normalizar_periodo(periodo: str | None) -> str:
    """
    Normaliza período a formato YYYY-MM.
    Acepta:
      - '2026-2'  -> '2026-02'
      - '2026/02' -> '2026-02'
      - ' 2026-02 ' -> '2026-02'
    Si no se puede normalizar, devuelve "".
    """
    s = (periodo or "").strip().replace("/", "-")
    if not s:
        return ""

    parts = s.split("-")
    if len(parts) != 2:
        return ""

    y_raw, m_raw = parts[0].strip(), parts[1].strip()
    if not (y_raw.isdigit() and m_raw.isdigit()):
        return ""

    y = int(y_raw)
    m = int(m_raw)

    if y < 1900 or y > 3000:
        return ""
    if m < 1 or m > 12:
        return ""

    return f"{y:04d}-{m:02d}"


def obtener_parametro_por_fecha(fecha: date | None) -> ParametroLaboral | None:
    """
    Devuelve el parámetro laboral vigente para una fecha dada.

    Regla:
    - fecha_vigencia_desde <= fecha <= fecha_vigencia_hasta
    - si hubiera más de uno por error, privilegia la vigencia más reciente
    """
    if not fecha:
        return None

    return (
        ParametroLaboral.query
        .filter(ParametroLaboral.fecha_vigencia_desde <= fecha)
        .filter(ParametroLaboral.fecha_vigencia_hasta >= fecha)
        .order_by(
            ParametroLaboral.fecha_vigencia_desde.desc(),
            ParametroLaboral.id.desc(),
        )
        .first()
    )


def obtener_parametro_por_periodo(periodo: str | None) -> ParametroLaboral | None:
    """
    Devuelve el parámetro laboral por período exacto YYYY-MM.
    """
    p = normalizar_periodo(periodo)
    if not p:
        return None

    return (
        ParametroLaboral.query
        .filter(ParametroLaboral.periodo == p)
        .first()
    )


def obtener_parametro_vigente(
    *,
    fecha: date | None = None,
    periodo: str | None = None,
    usar_fallback: bool = True,
) -> ParametroLaboral | None:
    """
    Helper principal y más flexible.

    Orden de búsqueda:
    1) Si viene fecha -> buscar por fecha
    2) Si viene período -> buscar por período
    3) Si usar_fallback=True:
       - si vino fecha y no encontró, intenta por período derivado de la fecha
       - si vino período y no encontró, devuelve el último registro anterior o igual al período
    """
    # 1) búsqueda por fecha
    if fecha:
        row = obtener_parametro_por_fecha(fecha)
        if row:
            return row

        if usar_fallback:
            periodo_fecha = periodo_from_date(fecha)
            row = obtener_parametro_por_periodo(periodo_fecha)
            if row:
                return row

    # 2) búsqueda por período
    if periodo:
        p = normalizar_periodo(periodo)
        if not p:
            return None

        row = obtener_parametro_por_periodo(p)
        if row:
            return row

        if usar_fallback:
            # Busca el último período anterior o igual
            row = (
                ParametroLaboral.query
                .filter(ParametroLaboral.periodo <= p)
                .order_by(ParametroLaboral.periodo.desc(), ParametroLaboral.id.desc())
                .first()
            )
            if row:
                return row

    return None


def obtener_ultimo_parametro() -> ParametroLaboral | None:
    """
    Devuelve el último parámetro laboral cargado, según período.
    Útil para autocompletar formularios o paneles admin.
    """
    return (
        ParametroLaboral.query
        .order_by(ParametroLaboral.periodo.desc(), ParametroLaboral.id.desc())
        .first()
    )


def existe_parametro_periodo(periodo: str | None, excluir_id: int | None = None) -> bool:
    """
    Valida si ya existe un registro para el período dado.
    Útil para formularios de creación/edición.
    """
    p = normalizar_periodo(periodo)
    if not p:
        return False

    q = ParametroLaboral.query.filter(ParametroLaboral.periodo == p)

    if excluir_id:
        q = q.filter(ParametroLaboral.id != excluir_id)

    return q.first() is not None


def resumen_parametro(row: ParametroLaboral | None) -> dict:
    """
    Devuelve un resumen serializable y seguro para UI / JSON.
    """
    if not row:
        return {}

    return {
        "id": row.id,
        "periodo": row.periodo or "",
        "fecha_vigencia_desde": row.fecha_vigencia_desde.isoformat() if row.fecha_vigencia_desde else "",
        "fecha_vigencia_hasta": row.fecha_vigencia_hasta.isoformat() if row.fecha_vigencia_hasta else "",
        "uf": str(row.uf) if row.uf is not None else "",
        "utm": str(row.utm) if row.utm is not None else "",
        "uta": str(row.uta) if row.uta is not None else "",
        "renta_minima_dependiente": str(row.renta_minima_dependiente) if row.renta_minima_dependiente is not None else "",
        "renta_minima_menor_mayor65": str(row.renta_minima_menor_mayor65) if row.renta_minima_menor_mayor65 is not None else "",
        "renta_minima_no_remuneracional": str(row.renta_minima_no_remuneracional) if row.renta_minima_no_remuneracional is not None else "",
        "tope_imponible_afp": str(row.tope_imponible_afp) if row.tope_imponible_afp is not None else "",
        "tope_imponible_inp": str(row.tope_imponible_inp) if row.tope_imponible_inp is not None else "",
        "tope_imponible_seguro_cesantia": str(row.tope_imponible_seguro_cesantia) if row.tope_imponible_seguro_cesantia is not None else "",
        "gratificacion_25_por_ciento_tope_mensual": str(row.gratificacion_25_por_ciento_tope_mensual) if row.gratificacion_25_por_ciento_tope_mensual is not None else "",
        "sueldo_minimo_para_gratificacion": str(row.sueldo_minimo_para_gratificacion) if row.sueldo_minimo_para_gratificacion is not None else "",
        "fuente": row.fuente or "",
        "fuente_documento": row.fuente_documento or "",
        "observaciones": row.observaciones or "",
    }