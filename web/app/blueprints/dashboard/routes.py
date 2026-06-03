# web/app/blueprints/dashboard/routes.py
from __future__ import annotations

import calendar
from datetime import date, timedelta

import sqlalchemy as sa
from decimal import Decimal
from flask import render_template, request
from flask_login import login_required, current_user

from ...auth.decorators import role_required
from ...extensions import db
from ...models import (
    Contrato,
    Trabajador,
    Obra,
    Empleador,
    Tercero,
    SolicitudFondos,
    SolicitudFondosItem,
    RendicionGasto,
    RendicionGastoItem,
    User,
)
from . import bp


# -----------------------------
# Helpers
# -----------------------------
def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    new_year = idx // 12
    new_month = (idx % 12) + 1
    return new_year, new_month

def _to_decimal_safe(v) -> Decimal:
    try:
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("0")

def _obras_accesibles_dashboard():
    q = Obra.query
    if hasattr(sa, "true") and False:
        pass

    from flask_login import current_user

    if current_user.has_role("ADMIN"):
        return q.order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc()).all()

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return []

    return (
        q.filter(Obra.id.in_(obra_ids))
        .order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc())
        .all()
    )


def _centros_costos_accesibles_dashboard():
    obras = _obras_accesibles_dashboard()
    return sorted({
        (o.centro_costo or "").strip()
        for o in obras
        if (o.centro_costo or "").strip()
    })

def _tipo_norm_case():
    t = sa.func.upper(sa.func.trim(sa.func.coalesce(Trabajador.tipo_trabajador, "")))
    return sa.case(
        (t.in_([sa.literal("DIRECTO"), sa.literal("DIRECTOS")]), sa.literal("DIRECTO")),
        else_=sa.literal("INDIRECTO"),
    ).label("tipo_norm")


def _kpi_contratos_activos(inicio_mes: date, fin_mes: date) -> dict[str, int]:
    contrato_activo_mes = sa.and_(
        Contrato.fecha_inicio.isnot(None),
        Contrato.fecha_inicio <= fin_mes,
        sa.or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= inicio_mes),
    )

    tipo_norm = _tipo_norm_case()
    contrato_id = Contrato.id

    directos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "DIRECTO", contrato_id), else_=None))
    )
    indirectos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "INDIRECTO", contrato_id), else_=None))
    )
    total_cnt = sa.func.count(sa.distinct(contrato_id))

    row = (
        db.session.query(
            total_cnt.label("total"),
            directos_cnt.label("directos"),
            indirectos_cnt.label("indirectos"),
        )
        .select_from(Contrato)
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
        .filter(contrato_activo_mes)
        .one()
    )

    return {
        "total": int(row.total or 0),
        "directos": int(row.directos or 0),
        "indirectos": int(row.indirectos or 0),
    }


def _por_empresa_en_mes(inicio_mes: date, fin_mes: date):
    """
    Retorna filas agregadas por empresa (razon_social) para el mes.
    """
    contrato_activo_mes = sa.and_(
        Contrato.fecha_inicio.isnot(None),
        Contrato.fecha_inicio <= fin_mes,
        sa.or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= inicio_mes),
    )

    tipo_norm = _tipo_norm_case()
    contrato_id = Contrato.id

    directos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "DIRECTO", contrato_id), else_=None))
    )
    indirectos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "INDIRECTO", contrato_id), else_=None))
    )
    total_cnt = sa.func.count(sa.distinct(contrato_id))

    return (
        db.session.query(
            Empleador.razon_social.label("empresa"),
            total_cnt.label("total"),
            directos_cnt.label("directos"),
            indirectos_cnt.label("indirectos"),
        )
        .select_from(Contrato)
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
        .join(Empleador, Empleador.id == Contrato.empleador_id)
        .filter(contrato_activo_mes)
        .group_by(Empleador.razon_social)
        .order_by(total_cnt.desc(), Empleador.razon_social.asc())
        .all()
    )


def _nombre_trabajador_expr():
    # "AP AP, NOMBRES" (robusto)
    ap_pat = sa.func.coalesce(Trabajador.ap_paterno, "")
    ap_mat = sa.func.coalesce(Trabajador.ap_materno, "")
    noms = sa.func.coalesce(Trabajador.nombres, "")
    apellidos = sa.func.trim(sa.func.concat(ap_pat, sa.literal(" "), ap_mat))
    return sa.func.trim(sa.func.concat(apellidos, sa.literal(", "), noms)).label("trabajador")

def _rut_completo_expr():
    """
    Arma rut completo '12345678-K' desde columnas Trabajador.rut y Trabajador.dv.
    Robusto: trim/upper y maneja dv nulo.
    """
    rut_num = sa.func.trim(sa.func.coalesce(Trabajador.rut, ""))
    dv = sa.func.upper(sa.func.trim(sa.func.coalesce(Trabajador.dv, "")))

    # Si no hay dv, devolvemos solo el rut (evita terminar en "12345678-")
    return sa.case(
        (dv != sa.literal(""), sa.func.concat(rut_num, sa.literal("-"), dv)),
        else_=rut_num,
    ).label("rut")

def _fecha_ingreso_efectiva_expr():
    """
    Fecha de ingreso efectiva:
    - usa Trabajador.fecha_ingreso_empresa si existe
    - si no, fallback al contrato más antiguo del trabajador
    """
    min_inicio_contrato_sq = (
        db.session.query(sa.func.min(Contrato.fecha_inicio))
        .filter(
            Contrato.trabajador_id == Trabajador.id,
            Contrato.fecha_inicio.isnot(None),
        )
        .correlate(Trabajador)
        .scalar_subquery()
    )

    return sa.func.coalesce(Trabajador.fecha_ingreso_empresa, min_inicio_contrato_sq)

def _next_anniversary_date_expr(ref_date: date, base_date_col):
    """
    Próxima ocurrencia anual (cumple/antigüedad) para base_date_col (date),
    usando el año de ref_date. Si ya pasó este año, suma 1 año.

    Fixes:
    - EXTRACT devuelve numeric -> casteamos a Integer
    - 29/02 en año no bisiesto -> ajusta a 28/02
    - return siempre DATE (no timestamp)
    """
    y = sa.literal(int(ref_date.year))

    m_num = sa.func.extract("month", base_date_col)
    d_num = sa.func.extract("day", base_date_col)

    m = sa.cast(m_num, sa.Integer)
    d = sa.cast(d_num, sa.Integer)

    # Año bisiesto:
    # divisible por 4 y (no por 100) o divisible por 400
    is_leap = sa.or_(
        sa.and_((y % 4) == 0, (y % 100) != 0),
        (y % 400) == 0,
    )

    # Si es 29/02 y no es bisiesto -> usamos 28
    d_safe = sa.case(
        (sa.and_(m == 2, d == 29, sa.not_(is_leap)), sa.literal(28)),
        else_=d,
    )

    this_year_date = sa.func.make_date(y, m, d_safe)

    # Si ya pasó este año, suma 1 año. Ojo: + interval da timestamp -> casteamos a DATE
    next_date = sa.case(
        (this_year_date < sa.literal(ref_date), this_year_date + sa.text("interval '1 year'")),
        else_=this_year_date,
    )

    return sa.cast(next_date, sa.Date)


# -----------------------------
# Dashboard Dotación mensual (existente)
# -----------------------------
@bp.get("/personal")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def personal_mes():
    year = int((request.args.get("year") or date.today().year))
    month = int((request.args.get("month") or date.today().month))

    inicio_mes, fin_mes = _month_bounds(year, month)

    # Mes anterior
    py, pm = _add_months(year, month, -1)
    inicio_prev, fin_prev = _month_bounds(py, pm)

    # KPI mes actual + prev
    kpi = _kpi_contratos_activos(inicio_mes, fin_mes)
    prev_kpi = _kpi_contratos_activos(inicio_prev, fin_prev)

    delta = {
        "total": kpi["total"] - prev_kpi["total"],
        "directos": kpi["directos"] - prev_kpi["directos"],
        "indirectos": kpi["indirectos"] - prev_kpi["indirectos"],
    }

    # Movimientos por CONTRATO (ingresos/egresos dentro del mes)
    ingresos_mes = (
        db.session.query(sa.func.count(sa.distinct(Contrato.id)))
        .filter(
            Contrato.fecha_inicio.isnot(None),
            Contrato.fecha_inicio >= inicio_mes,
            Contrato.fecha_inicio <= fin_mes,
        )
        .scalar()
        or 0
    )

    egresos_mes = (
        db.session.query(sa.func.count(sa.distinct(Contrato.id)))
        .filter(
            Contrato.fecha_termino.isnot(None),
            Contrato.fecha_termino >= inicio_mes,
            Contrato.fecha_termino <= fin_mes,
        )
        .scalar()
        or 0
    )

    # Rotación %: egresos / dotación promedio (simple)
    dot_prom = (kpi["total"] + prev_kpi["total"]) / 2.0 if (kpi["total"] + prev_kpi["total"]) else 0.0
    rotacion_pct = (egresos_mes / dot_prom * 100.0) if dot_prom > 0 else 0.0

    # -----------------------------
    # Tabla 1: Contratos por Obra (con centro de costo)
    # -----------------------------
    contrato_activo_mes = sa.and_(
        Contrato.fecha_inicio.isnot(None),
        Contrato.fecha_inicio <= fin_mes,
        sa.or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= inicio_mes),
    )

    tipo_norm = _tipo_norm_case()
    contrato_id = Contrato.id

    directos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "DIRECTO", contrato_id), else_=None))
    )
    indirectos_cnt = sa.func.count(
        sa.distinct(sa.case((tipo_norm == "INDIRECTO", contrato_id), else_=None))
    )
    total_cnt = sa.func.count(sa.distinct(contrato_id))

    cc_norm = sa.func.upper(sa.func.trim(sa.func.coalesce(Obra.centro_costo, "")))
    is_quintero_order = sa.case((cc_norm == sa.literal("QUINTERO"), 0), else_=1)

    por_obra = (
        db.session.query(
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            total_cnt.label("total"),
            directos_cnt.label("directos"),
            indirectos_cnt.label("indirectos"),
        )
        .select_from(Contrato)
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
        .join(Obra, Obra.id == Contrato.obra_id)
        .filter(contrato_activo_mes)
        .group_by(Obra.nombre, Obra.centro_costo)
        .order_by(is_quintero_order.asc(), total_cnt.desc(), Obra.nombre.asc())
        .all()
    )

    top_obras = sorted(por_obra, key=lambda r: (r.total or 0), reverse=True)[:5]

    # -----------------------------
    # Tabla 2: Contratos por Empresa (Empleador) + % + Δ vs mes anterior
    # -----------------------------
    por_empresa_cur = _por_empresa_en_mes(inicio_mes, fin_mes)
    por_empresa_prev = _por_empresa_en_mes(inicio_prev, fin_prev)

    prev_emp_map = {
        (r.empresa or "").strip(): {
            "total": int(r.total or 0),
            "directos": int(r.directos or 0),
            "indirectos": int(r.indirectos or 0),
        }
        for r in por_empresa_prev
    }

    total_mes = max(int(kpi["total"]), 0)

    por_empresa_enriched = []
    for r in por_empresa_cur:
        emp = (r.empresa or "").strip()
        tot = int(r.total or 0)
        dire = int(r.directos or 0)
        indi = int(r.indirectos or 0)

        prev_vals = prev_emp_map.get(emp, {"total": 0, "directos": 0, "indirectos": 0})
        d_tot = tot - int(prev_vals["total"])
        d_dir = dire - int(prev_vals["directos"])
        d_ind = indi - int(prev_vals["indirectos"])

        pct = (tot / total_mes * 100.0) if total_mes > 0 else 0.0

        por_empresa_enriched.append(
            {
                "empresa": emp,
                "total": tot,
                "directos": dire,
                "indirectos": indi,
                "pct": float(pct),
                "delta_total": int(d_tot),
                "delta_directos": int(d_dir),
                "delta_indirectos": int(d_ind),
            }
        )

    top_empresas = sorted(por_empresa_enriched, key=lambda x: x["total"], reverse=True)[:8]

    # -----------------------------
    # Tendencia 12 meses (incluye mes actual)
    # -----------------------------
    trend_12m: list[dict] = []
    for i in range(11, -1, -1):
        ty, tm = _add_months(year, month, -i)
        ti, tf = _month_bounds(ty, tm)
        tkpi = _kpi_contratos_activos(ti, tf)
        trend_12m.append(
            {
                "year": ty,
                "month": tm,
                "label": f"{tm:02d}/{ty}",
                "total": tkpi["total"],
                "directos": tkpi["directos"],
                "indirectos": tkpi["indirectos"],
            }
        )

    ctx = {
        "year": year,
        "month": month,
        "inicio_mes": inicio_mes,
        "fin_mes": fin_mes,
        "kpi": {
            **kpi,
            "ingresos": int(ingresos_mes),
            "egresos": int(egresos_mes),
        },
        "prev": {
            "year": py,
            "month": pm,
            **prev_kpi,
        },
        "delta": delta,
        "rotacion_pct": float(rotacion_pct),
        "por_obra": por_obra,
        "por_empresa": por_empresa_enriched,
        "top_obras": top_obras,
        "top_empresas": top_empresas,
        "trend_12m": trend_12m,
    }
    return render_template("dashboard/personal_mes.html", **ctx)


# -----------------------------
# Dashboard Bienestar (nuevo)
# -----------------------------
@bp.get("/bienestar")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def bienestar():
    today = date.today()
    days = int(request.args.get("days") or 30)
    until = today + timedelta(days=days)

    nombre_trab = _nombre_trabajador_expr()

    # Base: solo vigentes (bienestar para quienes están en cancha)
    base_trab_vig = sa.func.upper(sa.func.trim(sa.func.coalesce(Trabajador.estado_trabajador, ""))) == sa.literal("VIGENTE")

    rut_full = _rut_completo_expr()

    # -----------------------------
    # 1) Cumpleaños próximos
    # -----------------------------
    next_bday = _next_anniversary_date_expr(today, Trabajador.fecha_nacimiento).label("proxima_fecha")
    edad = sa.func.date_part("year", sa.func.age(sa.literal(today), Trabajador.fecha_nacimiento)).label("edad")
    dias_restantes = (next_bday - sa.literal(today)).label("dias_restantes")

    cumpleanos = (
        db.session.query(
            Trabajador.id.label("trabajador_id"),
            nombre_trab,
            rut_full,
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            next_bday,
            edad,
            dias_restantes,
        )
        .select_from(Trabajador)
        .join(Obra, Obra.id == Trabajador.obra_id)
        .filter(
            base_trab_vig,
            Trabajador.fecha_nacimiento.isnot(None),
            next_bday >= sa.literal(today),
            next_bday <= sa.literal(until),
        )
        .order_by(next_bday.asc(), nombre_trab.asc())
        .all()
    )

    # -----------------------------
    # 2) Aniversarios (antigüedad) próximos
    #    - usamos fecha_ingreso_empresa si existe
    #    - fallback: mínimo Contrato.fecha_inicio del trabajador (subquery)
    # -----------------------------
    fecha_ingreso_eff = _fecha_ingreso_efectiva_expr()
    next_anniv = _next_anniversary_date_expr(today, fecha_ingreso_eff).label("proxima_fecha")
    anios_antig = sa.func.date_part("year", sa.func.age(sa.literal(today), fecha_ingreso_eff)).label("anios")

    hitos = [1, 3, 5, 10, 15, 20]

    aniversarios = (
        db.session.query(
            Trabajador.id.label("trabajador_id"),
            nombre_trab,
            rut_full,
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            next_anniv,
            anios_antig,
        )
        .select_from(Trabajador)
        .join(Obra, Obra.id == Trabajador.obra_id)
        .filter(
            base_trab_vig,
            fecha_ingreso_eff.isnot(None),
            next_anniv >= sa.literal(today),
            next_anniv <= sa.literal(until),
            anios_antig.in_([sa.literal(x) for x in hitos]),
        )
        .order_by(next_anniv.asc(), anios_antig.desc(), nombre_trab.asc())
        .all()
    )

    # -----------------------------
    # 3) Ingresos recientes (últimos N días)
    # -----------------------------
    since = today - timedelta(days=days)

    ingresos = (
        db.session.query(
            Contrato.id.label("contrato_id"),
            Trabajador.id.label("trabajador_id"),
            nombre_trab,
            rut_full,
            Empleador.razon_social.label("empresa"),
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            Contrato.fecha_inicio.label("fecha"),
        )
        .select_from(Contrato)
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
        .join(Obra, Obra.id == Contrato.obra_id)
        .join(Empleador, Empleador.id == Contrato.empleador_id)
        .filter(
            base_trab_vig,
            Contrato.fecha_inicio.isnot(None),
            Contrato.fecha_inicio >= sa.literal(since),
            Contrato.fecha_inicio <= sa.literal(today),
        )
        .order_by(Contrato.fecha_inicio.desc(), nombre_trab.asc())
        .limit(50)
        .all()
    )

    # -----------------------------
    # 4) Contratos por vencer (próximos N días)
    # -----------------------------
    por_vencer = (
        db.session.query(
            Contrato.id.label("contrato_id"),
            Trabajador.id.label("trabajador_id"),
            nombre_trab,
            rut_full,
            Empleador.razon_social.label("empresa"),
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            Contrato.fecha_termino.label("fecha"),
        )
        .select_from(Contrato)
        .join(Trabajador, Trabajador.id == Contrato.trabajador_id)
        .join(Obra, Obra.id == Contrato.obra_id)
        .join(Empleador, Empleador.id == Contrato.empleador_id)
        .filter(
            base_trab_vig,
            Contrato.estado_contrato == "VIGENTE",
            Contrato.fecha_termino.isnot(None),
            Contrato.fecha_termino >= sa.literal(today),
            Contrato.fecha_termino <= sa.literal(until),
        )
        .order_by(Contrato.fecha_termino.asc(), nombre_trab.asc())
        .limit(100)
        .all()
    )

    # -----------------------------
    # 5) Top 10 trabajadores más antiguos
    # -----------------------------
    fecha_ingreso_eff = _fecha_ingreso_efectiva_expr()
    anios_servicio = sa.func.date_part("year", sa.func.age(sa.literal(today), fecha_ingreso_eff)).label("anios_servicio")

    mas_antiguos = (
        db.session.query(
            Trabajador.id.label("trabajador_id"),
            nombre_trab,
            rut_full,
            Empleador.razon_social.label("empresa"),
            Obra.nombre.label("obra"),
            Obra.centro_costo.label("centro_costo"),
            fecha_ingreso_eff.label("fecha_ingreso"),
            anios_servicio,
        )
        .select_from(Trabajador)
        .join(Obra, Obra.id == Trabajador.obra_id)
        .outerjoin(Contrato, Contrato.trabajador_id == Trabajador.id)
        .outerjoin(Empleador, Empleador.id == Contrato.empleador_id)
        .filter(
            base_trab_vig,
            fecha_ingreso_eff.isnot(None),
        )
        .group_by(
            Trabajador.id,
            Trabajador.rut,
            Trabajador.dv,
            Trabajador.ap_paterno,
            Trabajador.ap_materno,
            Trabajador.nombres,
            Empleador.razon_social,
            Obra.nombre,
            Obra.centro_costo,
            fecha_ingreso_eff,
        )
        .order_by(fecha_ingreso_eff.asc(), nombre_trab.asc())
        .limit(10)
        .all()
    )

    # KPIs simples
    kpi = {
        "cumpleanos": int(len(cumpleanos)),
        "aniversarios": int(len(aniversarios)),
        "ingresos": int(len(ingresos)),
        "vencen": int(len(por_vencer)),
    }

    ctx = {
        "today": today,
        "days": days,
        "until": until,
        "kpi": kpi,
        "cumpleanos": cumpleanos,
        "aniversarios": aniversarios,
        "ingresos": ingresos,
        "por_vencer": por_vencer,
        "mas_antiguos": mas_antiguos,
    }
    return render_template("dashboard/bienestar.html", **ctx)


@bp.get("/solicitudes-fondos")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def solicitudes_fondos():
    periodo_desde = (request.args.get("periodo_desde") or "").strip()   # YYYY-MM
    periodo_hasta = (request.args.get("periodo_hasta") or "").strip()   # YYYY-MM
    periodo_tipo = (request.args.get("periodo_tipo") or "").strip().upper()  # "", QUINCENA, FIN_MES
    centro_costo = (request.args.get("centro_costo") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()

    hoy = date.today()
    centros_costos = _centros_costos_accesibles_dashboard()

    # ---------------------------------
    # Validar / normalizar filtro tipo período
    # ---------------------------------
    if periodo_tipo not in ("", "QUINCENA", "FIN_MES"):
        periodo_tipo = ""

    # ---------------------------------
    # Período base: rango YYYY-MM a YYYY-MM
    # ---------------------------------
    def _parse_periodo_ym(value: str):
        try:
            y, m = map(int, value.split("-"))
            if m < 1 or m > 12:
                return None
            return y, m
        except Exception:
            return None

    parsed_desde = _parse_periodo_ym(periodo_desde)
    parsed_hasta = _parse_periodo_ym(periodo_hasta)

    if not parsed_desde and not parsed_hasta:
        # por defecto: mes actual
        parsed_desde = (hoy.year, hoy.month)
        parsed_hasta = (hoy.year, hoy.month)
        periodo_desde = f"{hoy.year:04d}-{hoy.month:02d}"
        periodo_hasta = f"{hoy.year:04d}-{hoy.month:02d}"
    elif parsed_desde and not parsed_hasta:
        parsed_hasta = parsed_desde
        periodo_hasta = periodo_desde
    elif parsed_hasta and not parsed_desde:
        parsed_desde = parsed_hasta
        periodo_desde = periodo_hasta

    year_desde, month_desde = parsed_desde
    year_hasta, month_hasta = parsed_hasta

    fecha_desde = date(year_desde, month_desde, 1)
    if month_hasta == 12:
        fecha_hasta = date(year_hasta + 1, 1, 1)
    else:
        fecha_hasta = date(year_hasta, month_hasta + 1, 1)

    # si el usuario invierte el rango, lo corregimos
    if fecha_hasta <= fecha_desde:
        if month_desde == 12:
            fecha_hasta = date(year_desde + 1, 1, 1)
        else:
            fecha_hasta = date(year_desde, month_desde + 1, 1)
        periodo_hasta = periodo_desde

    # ---------------------------------
    # Query base solicitudes
    # ---------------------------------
    q_sol = (
        db.session.query(
            SolicitudFondos.id,
            SolicitudFondos.numero,
            SolicitudFondos.centro_costo,
            SolicitudFondos.fecha_solicitud,
            SolicitudFondos.estado,
            SolicitudFondos.periodo_tipo,
            SolicitudFondos.obra_id,
            Obra.nombre.label("obra_nombre"),
        )
        .outerjoin(Obra, SolicitudFondos.obra_id == Obra.id)
        .filter(
            SolicitudFondos.fecha_solicitud >= fecha_desde,
            SolicitudFondos.fecha_solicitud < fecha_hasta,
        )
    )

    # Scope de acceso por centro de costo
    if not current_user.has_role("ADMIN"):
        if centros_costos:
            q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centros_costos))
        else:
            q_sol = q_sol.filter(sa.text("1=0"))

    if centro_costo:
        q_sol = q_sol.filter(SolicitudFondos.centro_costo == centro_costo)

    if estado:
        q_sol = q_sol.filter(SolicitudFondos.estado == estado)

    if periodo_tipo:
        q_sol = q_sol.filter(SolicitudFondos.periodo_tipo == periodo_tipo)

    solicitudes_rows = (
        q_sol.order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc())
        .all()
    )

    solicitud_ids = [int(r.id) for r in solicitudes_rows]

    # ---------------------------------
    # Totales por solicitud / sección
    # ---------------------------------
    totales_por_solicitud = {}
    totales_por_seccion = {
        "REMU": 0,
        "REND": 0,
        "TERC": 0,
        "VAR": 0,
    }

    if solicitud_ids:
        rows_items = (
            db.session.query(
                SolicitudFondosItem.solicitud_id.label("solicitud_id"),
                SolicitudFondosItem.seccion.label("seccion"),
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).label("total"),
            )
            .filter(SolicitudFondosItem.solicitud_id.in_(solicitud_ids))
            .group_by(SolicitudFondosItem.solicitud_id, SolicitudFondosItem.seccion)
            .all()
        )

        for row in rows_items:
            sid = int(row.solicitud_id)
            sec = (row.seccion or "").strip().upper()
            total = float(row.total or 0)

            if sid not in totales_por_solicitud:
                totales_por_solicitud[sid] = {
                    "REMU": 0,
                    "REND": 0,
                    "TERC": 0,
                    "VAR": 0,
                    "TOTAL": 0,
                }

            if sec in totales_por_solicitud[sid]:
                totales_por_solicitud[sid][sec] += total
                totales_por_seccion[sec] += total

        for sid in totales_por_solicitud:
            d = totales_por_solicitud[sid]
            d["TOTAL"] = d["REMU"] + d["REND"] + d["TERC"] + d["VAR"]

    # ---------------------------------
    # KPIs
    # ---------------------------------
    total_solicitudes = len(solicitudes_rows)
    total_general = sum(totales_por_seccion.values())
    ticket_promedio = (total_general / total_solicitudes) if total_solicitudes else 0

    # ---------------------------------
    # Resumen por centro de costo
    # ---------------------------------
    resumen_cc_map = {}

    for row in solicitudes_rows:
        cc = (row.centro_costo or "").strip() or "SIN CC"
        sid = int(row.id)
        total_sol = totales_por_solicitud.get(sid, {}).get("TOTAL", 0)

        if cc not in resumen_cc_map:
            resumen_cc_map[cc] = {
                "centro_costo": cc,
                "cantidad": 0,
                "total": 0,
                "ultima_fecha": None,
            }

        resumen_cc_map[cc]["cantidad"] += 1
        resumen_cc_map[cc]["total"] += total_sol

        f = row.fecha_solicitud
        if not resumen_cc_map[cc]["ultima_fecha"] or (f and f > resumen_cc_map[cc]["ultima_fecha"]):
            resumen_cc_map[cc]["ultima_fecha"] = f

    resumen_cc = sorted(
        resumen_cc_map.values(),
        key=lambda x: (x["total"], x["cantidad"]),
        reverse=True,
    )

    # ---------------------------------
    # Últimas solicitudes
    # ---------------------------------
    ultimas_solicitudes = []
    for row in solicitudes_rows[:10]:
        sid = int(row.id)
        ultimas_solicitudes.append(
            {
                "id": sid,
                "numero": row.numero,
                "fecha_solicitud": row.fecha_solicitud,
                "centro_costo": row.centro_costo,
                "estado": row.estado,
                "periodo_tipo": row.periodo_tipo,
                "obra_nombre": row.obra_nombre,
                "total": totales_por_solicitud.get(sid, {}).get("TOTAL", 0),
            }
        )

    # ---------------------------------
    # Evolución mensual (últimos 6 meses del universo filtrado por scope/cc/estado/tipo)
    # ---------------------------------
    q_hist = (
        db.session.query(
            sa.extract("year", SolicitudFondos.fecha_solicitud).label("anio"),
            sa.extract("month", SolicitudFondos.fecha_solicitud).label("mes"),
            SolicitudFondosItem.seccion.label("seccion"),
            sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).label("total"),
        )
        .join(SolicitudFondosItem, SolicitudFondosItem.solicitud_id == SolicitudFondos.id)
    )

    if not current_user.has_role("ADMIN"):
        if centros_costos:
            q_hist = q_hist.filter(SolicitudFondos.centro_costo.in_(centros_costos))
        else:
            q_hist = q_hist.filter(sa.text("1=0"))

    if centro_costo:
        q_hist = q_hist.filter(SolicitudFondos.centro_costo == centro_costo)

    if estado:
        q_hist = q_hist.filter(SolicitudFondos.estado == estado)

    if periodo_tipo:
        q_hist = q_hist.filter(SolicitudFondos.periodo_tipo == periodo_tipo)

    hist_rows = (
        q_hist.group_by(
            sa.extract("year", SolicitudFondos.fecha_solicitud),
            sa.extract("month", SolicitudFondos.fecha_solicitud),
            SolicitudFondosItem.seccion,
        )
        .order_by(
            sa.extract("year", SolicitudFondos.fecha_solicitud),
            sa.extract("month", SolicitudFondos.fecha_solicitud),
        )
        .all()
    )

    hist_map = {}
    for row in hist_rows:
        anio = int(row.anio)
        mes = int(row.mes)
        key = f"{anio:04d}-{mes:02d}"

        if key not in hist_map:
            hist_map[key] = {
                "periodo": key,
                "REMU": 0,
                "REND": 0,
                "TERC": 0,
                "VAR": 0,
                "TOTAL": 0,
            }

        sec = (row.seccion or "").strip().upper()
        total = float(row.total or 0)

        if sec in ("REMU", "REND", "TERC", "VAR"):
            hist_map[key][sec] += total
            hist_map[key]["TOTAL"] += total

    evolucion_meses = list(hist_map.values())[-6:]

    # ---------------------------------
    # Evolución del rango seleccionado
    # ---------------------------------
    meses_rango = (
        (year_hasta - year_desde) * 12
        + (month_hasta - month_desde)
        + 1
    )

    mostrar_evolucion_rango = meses_rango > 1

    serie_rango = []
    if mostrar_evolucion_rango:
        cursor_y = year_desde
        cursor_m = month_desde

        while (cursor_y < year_hasta) or (cursor_y == year_hasta and cursor_m <= month_hasta):
            key = f"{cursor_y:04d}-{cursor_m:02d}"
            data_mes = next((x for x in evolucion_meses if x["periodo"] == key), None)

            serie_rango.append({
                "periodo": key,
                "REMU": data_mes["REMU"] if data_mes else 0,
                "REND": data_mes["REND"] if data_mes else 0,
                "TERC": data_mes["TERC"] if data_mes else 0,
                "VAR": data_mes["VAR"] if data_mes else 0,
                "TOTAL": data_mes["TOTAL"] if data_mes else 0,
            })

            if cursor_m == 12:
                cursor_y += 1
                cursor_m = 1
            else:
                cursor_m += 1

    # ---------------------------------
    # Desglose REMU por tipo de trabajador
    # ---------------------------------
    remu_desglose = []

    if solicitud_ids:
        tipo_norm = sa.func.upper(sa.func.trim(sa.func.coalesce(Trabajador.tipo_trabajador, "")))

        tipo_label = sa.case(
            (tipo_norm.in_(["DIRECTO", "DIRECTOS"]), sa.literal("DIRECTO")),
            (tipo_norm.in_(["JEFATURA U OTROS", "JEFATURA Y OTROS"]), sa.literal("JEFATURA Y OTROS")),
            (tipo_norm == "", sa.literal("SIN TIPO")),
            else_=tipo_norm,
        )

        remu_rows = (
            db.session.query(
                tipo_label.label("tipo"),
                sa.func.count(SolicitudFondosItem.id).label("cantidad"),
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).label("total"),
            )
            .join(Trabajador, Trabajador.id == SolicitudFondosItem.trabajador_id)
            .filter(
                SolicitudFondosItem.solicitud_id.in_(solicitud_ids),
                SolicitudFondosItem.seccion == "REMU",
            )
            .group_by(tipo_label)
            .order_by(sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).desc())
            .all()
        )

        total_remu_base = _to_decimal_safe(totales_por_seccion.get("REMU", 0))

        for row in remu_rows:
            total_row = _to_decimal_safe(row.total)
            pct = float((total_row / total_remu_base) * 100) if total_remu_base > 0 else 0.0

            remu_desglose.append({
                "tipo": row.tipo or "SIN TIPO",
                "cantidad": int(row.cantidad or 0),
                "total": float(total_row),
                "pct": pct,
            })

    # ---------------------------------
    # Desglose REND por usuario que rindió
    # ---------------------------------
    rend_desglose = []

    if solicitud_ids:
        user_display = sa.func.coalesce(
            sa.func.nullif(User.nombre, ""),
            sa.func.nullif(User.username, ""),
            sa.literal("SIN USUARIO"),
        )

        rend_rows = (
            db.session.query(
                User.id.label("user_id"),
                user_display.label("trabajador"),
                sa.func.count(sa.distinct(RendicionGasto.id)).label("cantidad"),
                sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0).label("total"),
            )
            .select_from(RendicionGasto)
            .join(User, User.id == RendicionGasto.creado_por_user_id)
            .join(RendicionGastoItem, RendicionGastoItem.rendicion_id == RendicionGasto.id)
            .filter(RendicionGasto.solicitud_fondos_id.in_(solicitud_ids))
            .group_by(User.id, user_display)
            .order_by(sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0).desc())
            .limit(15)
            .all()
        )

        total_rend_base = _to_decimal_safe(totales_por_seccion.get("REND", 0))

        for row in rend_rows:
            total_row = _to_decimal_safe(row.total)
            cantidad = int(row.cantidad or 0)
            promedio = (total_row / cantidad) if cantidad > 0 else Decimal("0")
            pct = float((total_row / total_rend_base) * 100) if total_rend_base > 0 else 0.0

            rend_desglose.append({
                "trabajador_id": int(row.user_id or 0),
                "trabajador": (row.trabajador or "").strip(),
                "cantidad": cantidad,
                "total": float(total_row),
                "promedio": float(promedio),
                "pct": pct,
            })

    # ---------------------------------
    # Desglose TERC por beneficiario
    # ---------------------------------
    terc_desglose = []

    if solicitud_ids:
        tercero_nombre = sa.func.trim(
            sa.func.concat(
                sa.func.coalesce(Tercero.ap_paterno, ""),
                sa.literal(" "),
                sa.func.coalesce(Tercero.ap_materno, ""),
                sa.literal(" "),
                sa.func.coalesce(Tercero.nombres, ""),
            )
        )

        beneficiario_expr = sa.func.coalesce(
            sa.func.nullif(tercero_nombre, ""),
            sa.func.nullif(SolicitudFondosItem.beneficiario_nombre, ""),
            sa.func.nullif(SolicitudFondosItem.descripcion, ""),
            sa.literal("SIN IDENTIFICAR"),
        )

        terc_rows = (
            db.session.query(
                beneficiario_expr.label("beneficiario"),
                sa.func.count(SolicitudFondosItem.id).label("cantidad"),
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).label("total"),
            )
            .outerjoin(Tercero, Tercero.id == SolicitudFondosItem.tercero_id)
            .filter(
                SolicitudFondosItem.solicitud_id.in_(solicitud_ids),
                SolicitudFondosItem.seccion == "TERC",
            )
            .group_by(beneficiario_expr)
            .order_by(sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).desc())
            .limit(15)
            .all()
        )

        total_terc_base = _to_decimal_safe(totales_por_seccion.get("TERC", 0))

        for row in terc_rows:
            total_row = _to_decimal_safe(row.total)
            pct = float((total_row / total_terc_base) * 100) if total_terc_base > 0 else 0.0

            terc_desglose.append({
                "beneficiario": (row.beneficiario or "").strip(),
                "cantidad": int(row.cantidad or 0),
                "total": float(total_row),
                "pct": pct,
            })

    # ---------------------------------
    # Desglose VAR por beneficiario / descripción
    # ---------------------------------
    var_desglose = []

    if solicitud_ids:
        var_beneficiario_expr = sa.func.coalesce(
            sa.func.nullif(SolicitudFondosItem.beneficiario_nombre, ""),
            sa.func.nullif(SolicitudFondosItem.descripcion, ""),
            sa.literal("SIN IDENTIFICAR"),
        )

        var_rows = (
            db.session.query(
                var_beneficiario_expr.label("beneficiario"),
                sa.func.count(SolicitudFondosItem.id).label("cantidad"),
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).label("total"),
            )
            .filter(
                SolicitudFondosItem.solicitud_id.in_(solicitud_ids),
                SolicitudFondosItem.seccion == "VAR",
            )
            .group_by(var_beneficiario_expr)
            .order_by(sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0).desc())
            .limit(15)
            .all()
        )

        total_var_base = _to_decimal_safe(totales_por_seccion.get("VAR", 0))

        for row in var_rows:
            total_row = _to_decimal_safe(row.total)
            pct = float((total_row / total_var_base) * 100) if total_var_base > 0 else 0.0

            var_desglose.append({
                "beneficiario": (row.beneficiario or "").strip(),
                "cantidad": int(row.cantidad or 0),
                "total": float(total_row),
                "pct": pct,
            })

    return render_template(
        "dashboard/solicitudes_fondos.html",
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        periodo_tipo=periodo_tipo,
        centro_costo=centro_costo,
        estado=estado,
        centros_costos=centros_costos,
        total_solicitudes=total_solicitudes,
        total_general=total_general,
        ticket_promedio=ticket_promedio,
        totales_por_seccion=totales_por_seccion,
        resumen_cc=resumen_cc,
        ultimas_solicitudes=ultimas_solicitudes,
        evolucion_meses=evolucion_meses,
        mostrar_evolucion_rango=mostrar_evolucion_rango,
        serie_rango=serie_rango,
        remu_desglose=remu_desglose,
        rend_desglose=rend_desglose,
        terc_desglose=terc_desglose,
        var_desglose=var_desglose,
    )