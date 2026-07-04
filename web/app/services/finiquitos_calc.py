# web/app/services/finiquitos_calc.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Iterable

from ..models import Contrato, Desvinculacion, Feriado, Vacacion, VacacionMovimiento


DIAS_FERIADO_ANUAL = Decimal("15")
MESES_ANIO = Decimal("12")
DIAS_MES_LABORAL = Decimal("30")

# Versionado funcional del motor.
# Cada ajuste relevante de reglas/cálculo debe actualizar este valor para dejar
# trazabilidad en `calculo_finiquito` y en los respaldos administrativos.
FINIQUITO_ENGINE_VERSION = "finiquitos_v2026_07_01_phase4"
FINIQUITO_ENGINE_NAME = "Motor finiquitos Grupo CS"


def _to_decimal(v) -> Decimal:
    if v is None:
        return Decimal("0")
    s = str(v).strip()
    if not s:
        return Decimal("0")
    # Soporta entradas estilo chileno: 553.553 / 553553 / 4,13 / 1.234,56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round0(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _money(v: Decimal) -> str:
    n = int(_round0(v))
    return f"{n:,}".replace(",", ".")


def _dec2_es(v: Decimal) -> str:
    return f"{_round2(v):.2f}".replace(".", ",")


def _ceil_decimal_to_int(v: Decimal) -> int:
    if v <= 0:
        return 0
    return int(v.to_integral_value(rounding=ROUND_CEILING))


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


def diff_ymd_inclusivo(start: date, end: date) -> tuple[int, int, int]:
    """
    Diferencia calendario para remuneraciones/finiquito considerando ambos
    extremos del período trabajado.

    Ejemplo de control: 2026-03-16 a 2026-06-24 => 0 años, 3 meses y 9 días.
    """
    if end < start:
        start, end = end, start
    return diff_ymd(start, end + timedelta(days=1))


def meses_indemnizables(fecha_inicio: date | None, fecha_termino: date | None) -> int:
    if not fecha_inicio or not fecha_termino or fecha_termino < fecha_inicio:
        return 0

    anios, meses, dias = diff_ymd_inclusivo(fecha_inicio, fecha_termino)
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
    """
    Calcula el feriado proporcional en días hábiles con el criterio usado por
    la DT: 15/12 = 1,25 días hábiles por mes y 1,25/30 por día de fracción.

    El período se considera inclusivo para el tiempo efectivamente servido.
    Esto evita el desfase de 1 día observado en el caso 16-03-2026 / 24-06-2026.
    """
    fecha_base = fecha_base_feriado_proporcional(fecha_inicio, fecha_termino)
    if not fecha_base or not fecha_termino:
        return {
            "fecha_base": None,
            "dias_corridos_tramo": 0,
            "periodo_anios": 0,
            "periodo_meses": 0,
            "periodo_dias": 0,
            "dias_habiles_devengados": Decimal("0.00"),
        }

    dias_tramo = dias_corridos_trabajados_periodo(fecha_base, fecha_termino)
    anios, meses, dias = diff_ymd_inclusivo(fecha_base, fecha_termino)

    meses_totales = (Decimal(anios) * MESES_ANIO) + Decimal(meses)
    dias_por_mes = DIAS_FERIADO_ANUAL / MESES_ANIO  # 1,25
    dias_por_dia = dias_por_mes / DIAS_MES_LABORAL

    dias_habiles = _round2((meses_totales * dias_por_mes) + (Decimal(dias) * dias_por_dia))

    return {
        "fecha_base": fecha_base,
        "dias_corridos_tramo": dias_tramo,
        "periodo_anios": anios,
        "periodo_meses": meses,
        "periodo_dias": dias,
        "dias_habiles_devengados": dias_habiles,
    }


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

    # Si hay fracción, se necesita llegar al día hábil siguiente para cubrirla.
    dias_objetivo = _ceil_decimal_to_int(dias_habiles)
    if dias_objetivo <= 0 and dias_habiles > 0:
        dias_objetivo = 1

    cursor = fecha_inicio
    usados = 0

    while usados < dias_objetivo:
        if es_habil(cursor, feriados, sabado_habil=sabado_habil):
            usados += 1
            if usados == dias_objetivo:
                return cursor
        cursor += timedelta(days=1)

    return None


def sumar_dias_corridos_desde(fecha_inicio: date, dias_corridos: Decimal) -> date | None:
    if dias_corridos <= 0:
        return None

    # Si hay fracción, el período toca el día calendario siguiente.
    dias_enteros = _ceil_decimal_to_int(dias_corridos)
    if dias_enteros <= 0 and dias_corridos > 0:
        dias_enteros = 1

    return fecha_inicio + timedelta(days=max(dias_enteros - 1, 0))


def dias_corridos_equivalentes(
    dias_habiles: Decimal,
    fecha_inicio_corridos: date | None = None,
    feriados: set[date] | None = None,
    sabado_habil: bool = False,
) -> dict:
    """
    Convierte días hábiles de feriado a días corridos indemnizables.

    Antes se usaba el factor fijo 1,4. Eso falla cuando el período real incluye
    feriados específicos, como el 29-06-2026. Ahora se cuentan sábados,
    domingos y feriados reales desde el día siguiente al término del contrato.
    """
    dias_habiles = _round2(dias_habiles)
    if dias_habiles <= 0 or not fecha_inicio_corridos:
        return {
            "dias_habiles": Decimal("0.00"),
            "dias_inhabiles": Decimal("0.00"),
            "dias_corridos": Decimal("0.00"),
            "fecha_fin_habiles_ref": None,
            "fecha_fin_corridos": None,
        }

    feriados = feriados or set()
    dias_objetivo = _ceil_decimal_to_int(dias_habiles)

    cursor = fecha_inicio_corridos
    habiles_usados = 0
    inhabiles = 0
    fecha_fin_habiles_ref = None

    while habiles_usados < dias_objetivo:
        if es_habil(cursor, feriados, sabado_habil=sabado_habil):
            habiles_usados += 1
            if habiles_usados == dias_objetivo:
                fecha_fin_habiles_ref = cursor
                break
        else:
            inhabiles += 1
        cursor += timedelta(days=1)

    dias_inhabiles = Decimal(inhabiles)
    dias_corridos = _round2(dias_habiles + dias_inhabiles)

    return {
        "dias_habiles": dias_habiles,
        "dias_inhabiles": _round2(dias_inhabiles),
        "dias_corridos": dias_corridos,
        "fecha_fin_habiles_ref": fecha_fin_habiles_ref,
        "fecha_fin_corridos": sumar_dias_corridos_desde(fecha_inicio_corridos, dias_corridos),
    }


def resumen_movimientos_vacaciones(
    contrato_id: int,
    fecha_corte: date,
    movimientos: Iterable[VacacionMovimiento],
) -> dict:
    devengo = Decimal("0")
    uso = Decimal("0")
    ajuste = Decimal("0")
    uso_vacaciones_ids: set[int] = set()

    for mov in movimientos:
        if mov.contrato_id != contrato_id:
            continue
        if not mov.fecha or mov.fecha > fecha_corte:
            continue

        dias = _to_decimal(mov.dias)
        tipo = (mov.tipo or "").strip().upper()

        if tipo == "DEVENGO":
            devengo += dias
        elif tipo == "USO":
            # En el módulo de vacaciones el USO se guarda negativo. Para el
            # finiquito debe descontarse como cantidad positiva de días usados.
            uso += abs(dias)
            if mov.vacaciones_id:
                uso_vacaciones_ids.add(int(mov.vacaciones_id))
        elif tipo == "AJUSTE":
            # Se mantiene con signo: una anulación suma; un ajuste manual puede restar.
            ajuste += dias

    return {
        "devengo": _round2(devengo),
        "uso": _round2(uso),
        "ajuste": _round2(ajuste),
        "uso_vacaciones_ids": uso_vacaciones_ids,
    }


def resumen_vacaciones_emitidas(
    contrato_id: int,
    fecha_corte: date,
    vacaciones_emitidas: Iterable[Vacacion] | None,
    vacaciones_ya_en_movimientos: set[int] | None = None,
) -> dict:
    """
    Fallback para datos históricos: si existe un comprobante EMITIDO y no está
    representado en vacaciones_movimientos, igual se descuenta del finiquito.
    """
    usados = Decimal("0")
    ids_usados: set[int] = set()
    ids_mov = vacaciones_ya_en_movimientos or set()

    for vac in vacaciones_emitidas or []:
        if vac.contrato_id != contrato_id:
            continue
        if (vac.estado or "").strip().upper() != "EMITIDO":
            continue
        if vac.id and int(vac.id) in ids_mov:
            continue

        # Si la vacación ya comenzó al corte, corresponde considerarla usada.
        fecha_inicio = getattr(vac, "fecha_inicio", None)
        if fecha_inicio and fecha_inicio > fecha_corte:
            continue

        dias = _to_decimal(getattr(vac, "dias_habiles", 0))
        if dias > 0:
            usados += dias
            if vac.id:
                ids_usados.add(int(vac.id))

    return {
        "uso": _round2(usados),
        "ids": ids_usados,
    }


def saldo_feriado_para_finiquito(
    fecha_inicio: date | None,
    fecha_termino: date | None,
    contrato_id: int,
    movimientos: Iterable[VacacionMovimiento],
    vacaciones_emitidas: Iterable[Vacacion] | None = None,
) -> dict:
    dev = dias_feriado_devengados_proporcionales(fecha_inicio, fecha_termino)
    devengo_teorico = dev["dias_habiles_devengados"]

    movs = resumen_movimientos_vacaciones(contrato_id, fecha_termino, movimientos)
    fallback_vac = resumen_vacaciones_emitidas(
        contrato_id=contrato_id,
        fecha_corte=fecha_termino,
        vacaciones_emitidas=vacaciones_emitidas,
        vacaciones_ya_en_movimientos=movs["uso_vacaciones_ids"],
    )

    devengo_movimientos = movs["devengo"]
    dias_usados = movs["uso"] + fallback_vac["uso"]
    dias_ajuste = movs["ajuste"]

    saldo = devengo_teorico + devengo_movimientos - dias_usados + dias_ajuste
    if saldo < 0:
        saldo = Decimal("0")

    return {
        "fecha_base_proporcional": dev["fecha_base"],
        "dias_corridos_tramo": int(dev["dias_corridos_tramo"]),
        "periodo_anios": int(dev["periodo_anios"]),
        "periodo_meses": int(dev["periodo_meses"]),
        "periodo_dias": int(dev["periodo_dias"]),
        "devengo_teorico": _round2(devengo_teorico),
        "devengo_movimientos": _round2(devengo_movimientos),
        "dias_usados": _round2(dias_usados),
        "dias_usados_movimientos": _round2(movs["uso"]),
        "dias_usados_fallback_vacaciones": _round2(fallback_vac["uso"]),
        "dias_ajuste": _round2(dias_ajuste),
        "dias_a_pago": _round2(saldo),
        # Se completa más abajo con feriados reales, porque depende de la fecha
        # de inicio del período indemnizable y del calendario de feriados.
        "dias_inhabiles_periodo": Decimal("0.00"),
        "dias_corridos_equivalentes": Decimal("0.00"),
    }


def valor_dia_corrido(base_mensual: Decimal) -> Decimal:
    return _round2(base_mensual / Decimal("30"))


def monto_feriado(base_mensual: Decimal, dias_corridos: Decimal) -> Decimal:
    return _round2(valor_dia_corrido(base_mensual) * dias_corridos)


def promedio_variables(m1, m2, m3) -> Decimal:
    vals = [_to_decimal(m1), _to_decimal(m2), _to_decimal(m3)]
    return _round2(sum(vals) / Decimal("3"))


def base_feriado(
    contrato: Contrato,
    tipo_remuneracion: str = "FIJA",
    promedio_variable: Decimal | None = None,
    incluir_colacion: bool = False,
    incluir_movilizacion: bool = False,
) -> dict:
    """
    Base del feriado proporcional.

    Regla operativa del sistema:
    - FIJA: sueldo base.
    - VARIABLE/MIXTA: sueldo base + promedio de variables de los últimos 3 meses.

    Nota importante: en nuestros contratos de construcción, el trabajador puede
    tener sueldo base y además componentes variables (tratos, bonos u otros
    haberes computables). Por eso la opción VARIABLE no debe reemplazar el
    sueldo base por el promedio variable; debe sumarlo.

    La gratificación mensual no se incluye en feriado proporcional.
    Colación/movilización quedan sólo como override manual de la UI.
    """
    tipo = (tipo_remuneracion or "FIJA").strip().upper()
    sueldo_base = _to_decimal(contrato.sueldo_base)
    colacion = _to_decimal(contrato.asignacion_colacion) if incluir_colacion else Decimal("0")
    movilizacion = _to_decimal(contrato.asignacion_movilizacion) if incluir_movilizacion else Decimal("0")
    variable = _round2(promedio_variable or Decimal("0"))

    if tipo in {"VARIABLE", "MIXTA"}:
        total = sueldo_base + variable + colacion + movilizacion
        sueldo_para_total = sueldo_base
    else:
        total = sueldo_base + colacion + movilizacion
        sueldo_para_total = sueldo_base

    total = _round2(total)

    return {
        "sueldo_base": _round2(sueldo_para_total),
        "colacion": _round2(colacion),
        "movilizacion": _round2(movilizacion),
        "gratificacion": Decimal("0"),
        "promedio_variable": _round2(variable),
        "total": total,
    }


def base_fija_feriado(
    contrato: Contrato,
    incluir_colacion: bool = False,
    incluir_movilizacion: bool = False,
) -> dict:
    # Compatibilidad con cualquier import antiguo.
    return base_feriado(
        contrato=contrato,
        tipo_remuneracion="FIJA",
        promedio_variable=Decimal("0"),
        incluir_colacion=incluir_colacion,
        incluir_movilizacion=incluir_movilizacion,
    )


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

    tipo = (tipo_remuneracion or "FIJA").strip().upper()
    fijo = sueldo_base + colacion + movilizacion + gratificacion

    if tipo == "FIJA":
        total = fijo
    else:
        # VARIABLE y MIXTA representan remuneración fija con haberes variables:
        # sueldo base + promedio variable + componentes indemnizatorios marcados.
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
    vacaciones_emitidas: Iterable[Vacacion] | None = None,
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

    base_fer = base_feriado(
        contrato=contrato,
        tipo_remuneracion=tipo_remuneracion,
        promedio_variable=promedio_var,
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
        vacaciones_emitidas=vacaciones_emitidas,
    )

    dias_vac = vac["dias_a_pago"]
    fecha_inicio_corridos = fecha_termino + timedelta(days=1) if fecha_termino else None
    feriados_set = obtener_feriados_set(feriados_rows)

    corridos = dias_corridos_equivalentes(
        dias_habiles=dias_vac,
        fecha_inicio_corridos=fecha_inicio_corridos,
        feriados=feriados_set,
        sabado_habil=False,
    )
    dias_corridos = corridos["dias_corridos"]
    monto_fer = monto_feriado(base_fer["total"], dias_corridos)

    aviso = base_indem["total"] if aplicar_aviso_previo else Decimal("0")

    meses_indem = meses_indemnizables(fecha_inicio, fecha_termino) if aplicar_anios_servicio else 0
    if tope_meses_anios_servicio is not None:
        meses_indem = min(meses_indem, int(tope_meses_anios_servicio))

    anios_serv = _round2(base_indem["total"] * Decimal(str(meses_indem)))

    y, m, d = diff_ymd_inclusivo(fecha_inicio, fecha_termino) if fecha_inicio and fecha_termino else (0, 0, 0)

    return {
        "engine": {
            "name": FINIQUITO_ENGINE_NAME,
            "version": FINIQUITO_ENGINE_VERSION,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "calculation_engine_version": FINIQUITO_ENGINE_VERSION,
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
            "promedio_variable": _money(base_fer["promedio_variable"]),
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
        "periodo_proporcional": {
            "anios": vac["periodo_anios"],
            "meses": vac["periodo_meses"],
            "dias": vac["periodo_dias"],
        },
        "periodo_proporcional_txt": f"{vac['periodo_anios']} años {vac['periodo_meses']} meses {vac['periodo_dias']} días",

        "feriado_devengado_teorico_habiles": _dec2_es(vac["devengo_teorico"]),
        "feriado_devengado_movimientos": _dec2_es(vac["devengo_movimientos"]),
        "feriado_dias_usados_habiles": _dec2_es(vac["dias_usados"]),
        "feriado_dias_usados_movimientos": _dec2_es(vac["dias_usados_movimientos"]),
        "feriado_dias_usados_fallback_vacaciones": _dec2_es(vac["dias_usados_fallback_vacaciones"]),
        "feriado_dias_ajuste": _dec2_es(vac["dias_ajuste"]),
        "feriado_dias_inhabiles": _dec2_es(corridos["dias_inhabiles"]),
        "dias_feriado_habiles": _dec2_es(dias_vac),
        "dias_feriado_corridos": _dec2_es(dias_corridos),

        "monto_feriado": _money(monto_fer),
        "fecha_inicio_corridos": fecha_inicio_corridos.isoformat() if fecha_inicio_corridos else "",
        "fecha_fin_corridos": corridos["fecha_fin_corridos"].isoformat() if corridos["fecha_fin_corridos"] else "",
        "fecha_fin_habiles_ref": corridos["fecha_fin_habiles_ref"].isoformat() if corridos["fecha_fin_habiles_ref"] else "",

        "aviso_previo": _money(aviso) if aplicar_aviso_previo else "",
        "meses_indemnizables": meses_indem,
        "anios_servicio": _money(anios_serv) if aplicar_anios_servicio else "",

        "tiempo_servido": {
            "anios": y,
            "meses": m,
            "dias": d,
        },
    }
