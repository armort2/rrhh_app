# web/app/services/finiquitos_calc.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from ..models import Contrato, Desvinculacion, Feriado, VacacionMovimiento


def _to_decimal(v) -> Decimal:
    if v is None:
        return Decimal("0")
    s = str(v).strip()
    if not s:
        return Decimal("0")
    s = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s
    return Decimal(s)


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round0(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _money(v: Decimal) -> str:
    n = int(_round0(v))
    return f"{n:,}".replace(",", ".")


def _days_in_month(y: int, m: int) -> int:
    if m == 2:
        leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
        return 29 if leap else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def diff_ymd(start: date, end: date) -> tuple[int, int, int]:
    if end < start:
        start, end = end, start

    y = end.year - start.year
    m = end.month - start.month
    d = end.day - start.day

    if d < 0:
        m -= 1
        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month > 1 else end.year - 1
        d += _days_in_month(prev_year, prev_month)

    if m < 0:
        y -= 1
        m += 12

    return max(y, 0), max(m, 0), max(d, 0)


def meses_indemnizables(fecha_inicio: date | None, fecha_termino: date | None) -> int:
    if not fecha_inicio or not fecha_termino or fecha_termino < fecha_inicio:
        return 0

    anios, meses, dias = diff_ymd(fecha_inicio, fecha_termino)
    total = anios
    if meses > 6 or (meses == 6 and dias > 0):
        total += 1
    return total


def dias_corridos_trabajados_periodo(fecha_desde: date | None, fecha_hasta: date | None) -> int:
    if not fecha_desde or not fecha_hasta or fecha_hasta < fecha_desde:
        return 0
    return (fecha_hasta - fecha_desde).days + 1


def fecha_base_feriado_proporcional(fecha_inicio: date | None, fecha_termino: date | None) -> date | None:
    if not fecha_inicio or not fecha_termino or fecha_termino < fecha_inicio:
        return None

    base = fecha_inicio

    while True:
        try:
            siguiente_anualidad = base.replace(year=base.year + 1)
        except ValueError:
            siguiente_anualidad = base.replace(year=base.year + 1, day=28)

        if siguiente_anualidad <= fecha_termino:
            base = siguiente_anualidad
        else:
            break

    return base


def dias_feriado_devengados_proporcionales(
    fecha_inicio: date | None,
    fecha_termino: date | None,
) -> dict:
    fecha_base = fecha_base_feriado_proporcional(fecha_inicio, fecha_termino)
    if not fecha_base or not fecha_termino:
        return {
            "fecha_base": None,
            "dias_corridos_tramo": 0,
            "dias_habiles_devengados": Decimal("0.00"),
        }

    dias_tramo = dias_corridos_trabajados_periodo(fecha_base, fecha_termino)
    dias_habiles = _round2((Decimal(dias_tramo) * Decimal("15")) / Decimal("365"))

    return {
        "fecha_base": fecha_base,
        "dias_corridos_tramo": dias_tramo,
        "dias_habiles_devengados": dias_habiles,
    }


def dias_corridos_equivalentes(dias_habiles: Decimal) -> Decimal:
    if dias_habiles <= 0:
        return Decimal("0")
    return _round2(dias_habiles * Decimal("1.4"))


def resumen_movimientos_vacaciones(
    contrato_id: int,
    fecha_corte: date,
    movimientos: Iterable[VacacionMovimiento],
) -> dict:
    devengo = Decimal("0")
    uso = Decimal("0")
    ajuste = Decimal("0")

    for mov in movimientos:
        if mov.contrato_id != contrato_id:
            continue
        if not mov.fecha or mov.fecha > fecha_corte:
            continue

        dias = _to_decimal(mov.dias)

        if mov.tipo == "DEVENGO":
            devengo += dias
        elif mov.tipo == "USO":
            uso += dias
        elif mov.tipo == "AJUSTE":
            ajuste += dias

    return {
        "devengo": _round2(devengo),
        "uso": _round2(uso),
        "ajuste": _round2(ajuste),
    }


def saldo_feriado_para_finiquito(
    fecha_inicio: date | None,
    fecha_termino: date | None,
    contrato_id: int,
    movimientos: Iterable[VacacionMovimiento],
) -> dict:
    dev = dias_feriado_devengados_proporcionales(fecha_inicio, fecha_termino)
    devengo_teorico = dev["dias_habiles_devengados"]

    movs = resumen_movimientos_vacaciones(contrato_id, fecha_termino, movimientos)

    dias_usados = movs["uso"]
    dias_ajuste = movs["ajuste"]

    saldo = devengo_teorico - dias_usados + dias_ajuste
    if saldo < 0:
        saldo = Decimal("0")

    dias_corridos = dias_corridos_equivalentes(saldo)

    return {
        "fecha_base_proporcional": dev["fecha_base"],
        "dias_corridos_tramo": int(dev["dias_corridos_tramo"]),
        "devengo_teorico": _round2(devengo_teorico),
        "dias_usados": _round2(dias_usados),
        "dias_ajuste": _round2(dias_ajuste),
        "dias_a_pago": _round2(saldo),
        "dias_corridos_equivalentes": _round2(dias_corridos),
    }


def valor_dia_corrido(base_mensual: Decimal) -> Decimal:
    return _round2(base_mensual / Decimal("30"))


def monto_feriado(base_mensual: Decimal, dias_habiles: Decimal) -> Decimal:
    dias_corridos = dias_corridos_equivalentes(dias_habiles)
    return _round2(valor_dia_corrido(base_mensual) * dias_corridos)


def obtener_feriados_set(rows: Iterable[Feriado]) -> set[date]:
    return {r.fecha for r in rows if r.activo and r.fecha}


def es_habil(fecha: date, feriados: set[date], sabado_habil: bool = False) -> bool:
    if fecha in feriados:
        return False

    wd = fecha.weekday()

    if wd == 6:
        return False

    if wd == 5 and not sabado_habil:
        return False

    return True


def sumar_dias_habiles_desde(
    fecha_inicio: date,
    dias_habiles: Decimal,
    feriados: set[date],
    sabado_habil: bool = False,
) -> date | None:
    if dias_habiles <= 0:
        return None

    dias_enteros = int(dias_habiles.to_integral_value(rounding=ROUND_HALF_UP))
    if dias_enteros <= 0 and dias_habiles > 0:
        dias_enteros = 1

    cursor = fecha_inicio
    usados = 0

    while usados < dias_enteros:
        if es_habil(cursor, feriados, sabado_habil=sabado_habil):
            usados += 1
            if usados == dias_enteros:
                return cursor
        cursor += timedelta(days=1)

    return None


def sumar_dias_corridos_desde(fecha_inicio: date, dias_corridos: Decimal) -> date | None:
    if dias_corridos <= 0:
        return None

    dias_enteros = int(dias_corridos.to_integral_value(rounding=ROUND_HALF_UP))
    if dias_enteros <= 0 and dias_corridos > 0:
        dias_enteros = 1

    return fecha_inicio + timedelta(days=max(dias_enteros - 1, 0))


def promedio_variables(m1, m2, m3) -> Decimal:
    vals = [_to_decimal(m1), _to_decimal(m2), _to_decimal(m3)]
    return _round2(sum(vals) / Decimal("3"))


def base_fija_feriado(
    contrato: Contrato,
    incluir_colacion: bool = False,
    incluir_movilizacion: bool = False,
) -> dict:
    sueldo_base = _to_decimal(contrato.sueldo_base)
    colacion = _to_decimal(contrato.asignacion_colacion) if incluir_colacion else Decimal("0")
    movilizacion = _to_decimal(contrato.asignacion_movilizacion) if incluir_movilizacion else Decimal("0")

    total = _round2(sueldo_base + colacion + movilizacion)

    return {
        "sueldo_base": _round2(sueldo_base),
        "colacion": _round2(colacion),
        "movilizacion": _round2(movilizacion),
        "gratificacion": Decimal("0"),
        "total": total,
    }


def base_indemnizacion(
    contrato: Contrato,
    tipo_remuneracion: str = "FIJA",
    promedio_variable: Decimal | None = None,
    incluir_gratificacion: bool = False,
    gratificacion_mensual: Decimal | None = None,
    incluir_colacion: bool = False,
    incluir_movilizacion: bool = False,
) -> dict:
    sueldo_base = _to_decimal(contrato.sueldo_base)
    colacion = _to_decimal(contrato.asignacion_colacion) if incluir_colacion else Decimal("0")
    movilizacion = _to_decimal(contrato.asignacion_movilizacion) if incluir_movilizacion else Decimal("0")
    gratificacion = _round2(gratificacion_mensual or Decimal("0")) if incluir_gratificacion else Decimal("0")
    variable = _round2(promedio_variable or Decimal("0"))

    fijo = sueldo_base + colacion + movilizacion + gratificacion

    if tipo_remuneracion == "FIJA":
        total = fijo
    elif tipo_remuneracion == "VARIABLE":
        total = variable
    else:
        total = fijo + variable

    total = _round2(total)

    return {
        "sueldo_base": _round2(sueldo_base),
        "gratificacion": _round2(gratificacion),
        "colacion": _round2(colacion),
        "movilizacion": _round2(movilizacion),
        "promedio_variable": _round2(variable),
        "total": total,
    }


def calcular_resumen_finiquito(
    desv: Desvinculacion,
    movimientos: Iterable[VacacionMovimiento],
    feriados_rows: Iterable[Feriado],
    tipo_remuneracion: str = "FIJA",
    var1: str | int | float | None = None,
    var2: str | int | float | None = None,
    var3: str | int | float | None = None,
    aplicar_aviso_previo: bool = False,
    aplicar_anios_servicio: bool = False,
    incluir_colacion_base: bool = False,
    incluir_movilizacion_base: bool = False,
    incluir_gratificacion_base: bool = False,
    gratificacion_mensual: str | int | float | None = None,
    tope_meses_anios_servicio: int | None = 11,
) -> dict:
    contrato = desv.contrato
    fecha_termino = desv.fecha_termino
    fecha_inicio = contrato.fecha_inicio

    promedio_var = promedio_variables(var1, var2, var3) if tipo_remuneracion in {"VARIABLE", "MIXTA"} else Decimal("0")
    gratificacion_valor = _to_decimal(gratificacion_mensual)

    base_fer = base_fija_feriado(
        contrato,
        incluir_colacion=incluir_colacion_base,
        incluir_movilizacion=incluir_movilizacion_base,
    )

    base_indem = base_indemnizacion(
        contrato=contrato,
        tipo_remuneracion=tipo_remuneracion,
        promedio_variable=promedio_var,
        incluir_gratificacion=incluir_gratificacion_base,
        gratificacion_mensual=gratificacion_valor,
        incluir_colacion=incluir_colacion_base,
        incluir_movilizacion=incluir_movilizacion_base,
    )

    vac = saldo_feriado_para_finiquito(
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
        contrato_id=contrato.id,
        movimientos=movimientos,
    )

    dias_vac = vac["dias_a_pago"]
    dias_corridos = vac["dias_corridos_equivalentes"]
    monto_fer = monto_feriado(base_fer["total"], dias_vac)

    fecha_inicio_corridos = fecha_termino + timedelta(days=1) if fecha_termino else None

    feriados_set = obtener_feriados_set(feriados_rows)

    fecha_fin_corridos = (
        sumar_dias_corridos_desde(fecha_inicio_corridos, dias_corridos)
        if fecha_inicio_corridos and dias_corridos > 0
        else None
    )

    fecha_fin_habiles_ref = (
        sumar_dias_habiles_desde(fecha_inicio_corridos, dias_vac, feriados_set, sabado_habil=False)
        if fecha_inicio_corridos and dias_vac > 0
        else None
    )

    aviso = base_indem["total"] if aplicar_aviso_previo else Decimal("0")

    meses_indem = meses_indemnizables(fecha_inicio, fecha_termino) if aplicar_anios_servicio else 0
    if tope_meses_anios_servicio is not None:
        meses_indem = min(meses_indem, int(tope_meses_anios_servicio))

    anios_serv = _round2(base_indem["total"] * Decimal(str(meses_indem)))

    y, m, d = diff_ymd(fecha_inicio, fecha_termino) if fecha_inicio and fecha_termino else (0, 0, 0)

    return {
        "tipo_remuneracion": tipo_remuneracion,

        "base_fija": _money(base_fer["total"]),
        "promedio_variable": _money(promedio_var),

        "base_calculo": _money(base_fer["total"]),
        "base_feriado": _money(base_fer["total"]),
        "base_indemnizacion": _money(base_indem["total"]),

        "detalle_base_feriado": {
            "sueldo_base": _money(base_fer["sueldo_base"]),
            "gratificacion": _money(base_fer["gratificacion"]),
            "colacion": _money(base_fer["colacion"]),
            "movilizacion": _money(base_fer["movilizacion"]),
            "total": _money(base_fer["total"]),
        },

        "detalle_base_indemnizacion": {
            "sueldo_base": _money(base_indem["sueldo_base"]),
            "gratificacion": _money(base_indem["gratificacion"]),
            "colacion": _money(base_indem["colacion"]),
            "movilizacion": _money(base_indem["movilizacion"]),
            "promedio_variable": _money(base_indem["promedio_variable"]),
            "total": _money(base_indem["total"]),
        },

        "fecha_base_proporcional": vac["fecha_base_proporcional"].isoformat() if vac["fecha_base_proporcional"] else "",
        "dias_corridos_tramo_proporcional": vac["dias_corridos_tramo"],

        "feriado_devengado_teorico_habiles": str(vac["devengo_teorico"]).replace(".", ","),
        "feriado_dias_usados_habiles": str(vac["dias_usados"]).replace(".", ","),
        "feriado_dias_ajuste": str(vac["dias_ajuste"]).replace(".", ","),
        "dias_feriado_habiles": str(dias_vac).replace(".", ","),
        "dias_feriado_corridos": str(dias_corridos).replace(".", ","),

        "monto_feriado": _money(monto_fer),
        "fecha_inicio_corridos": fecha_inicio_corridos.isoformat() if fecha_inicio_corridos else "",
        "fecha_fin_corridos": fecha_fin_corridos.isoformat() if fecha_fin_corridos else "",
        "fecha_fin_habiles_ref": fecha_fin_habiles_ref.isoformat() if fecha_fin_habiles_ref else "",

        "aviso_previo": _money(aviso) if aplicar_aviso_previo else "",
        "meses_indemnizables": meses_indem,
        "anios_servicio": _money(anios_serv) if aplicar_anios_servicio else "",

        "tiempo_servido": {
            "anios": y,
            "meses": m,
            "dias": d,
        },
    }