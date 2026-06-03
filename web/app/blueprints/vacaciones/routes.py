from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
import unicodedata
from decimal import Decimal

from flask import (
    render_template, request, redirect, url_for, flash, abort, current_app
)
from flask_login import login_required, current_user
from sqlalchemy import func

from docx import Document

from ...extensions import db
from ...models import Contrato, Vacacion, VacacionMovimiento, Feriado
from ...services.docx_engine import replace_placeholders
from ...services.pdf_convert import convert_docx_to_pdf
from ...services.paths_nextcloud import get_nc_paths
from ...services.storage_nextcloud_fs import ensure_dir, safe_write_bytes
from ...utils import fecha_larga_es

from . import bp


# ==========================
# Helpers
# ==========================

def _format_rut_con_puntos(rut: str | None) -> str:
    """
    Recibe rut tipo '13229458-5' o '132294585'
    Devuelve '13.229.458-5'
    """
    if not rut:
        return "-"

    rut = rut.replace(".", "").strip().upper()

    if "-" in rut:
        cuerpo, dv = rut.split("-")
    else:
        cuerpo, dv = rut[:-1], rut[-1]

    if not cuerpo.isdigit():
        return rut

    cuerpo_rev = cuerpo[::-1]
    partes = [cuerpo_rev[i:i+3] for i in range(0, len(cuerpo_rev), 3)]
    cuerpo_formateado = ".".join(part[::-1] for part in partes[::-1])

    return f"{cuerpo_formateado}-{dv}"

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=sábado, 6=domingo


def _feriados_set_between(d1: date, d2: date) -> set[date]:
    """
    Retorna set de feriados entre d1 y d2 (inclusive).
    """
    if not d1 or not d2:
        return set()
    start = min(d1, d2)
    end = max(d1, d2)

    rows = (
        db.session.query(Feriado.fecha)
        .filter(Feriado.fecha >= start)
        .filter(Feriado.fecha <= end)
        .all()
    )
    return {r[0] for r in rows}


def _is_non_working(d: date, feriados: set[date]) -> bool:
    """
    No hábil = fin de semana o feriado.
    """
    return _is_weekend(d) or (d in feriados)


def _count_business_days(d1: date, d2: date, *, feriados: set[date] | None = None) -> int:
    """
    Cuenta días hábiles (L-V) excluyendo feriados, incluyendo ambos extremos.
    """
    if not d1 or not d2 or d2 < d1:
        return 0

    fer = feriados or set()
    n = 0
    cur = d1
    while cur <= d2:
        if not _is_non_working(cur, fer):
            n += 1
        cur += timedelta(days=1)
    return n


def _next_business_day(d: date, *, feriados: set[date] | None = None) -> date:
    fer = feriados or set()
    cur = d
    while _is_non_working(cur, fer):
        cur += timedelta(days=1)
    return cur


def _calc_retorno(fecha_termino: date, *, feriados: set[date] | None = None) -> date:
    """
    Retorno = día siguiente hábil posterior a término (saltando feriados).
    """
    cur = fecha_termino + timedelta(days=1)
    return _next_business_day(cur, feriados=feriados)


def _months_between(start: date, end: date) -> int:
    """Meses completos entre start y end (end >= start)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _dias_vacaciones_acumulados(fecha_inicio_contrato: date | None, as_of: date) -> int:
    """
    MVP conservador:
    - 0 días antes de 12 meses completos
    - luego 1.25 días/mes (15/12) por mes completo trabajado
    - redondeo hacia abajo (días enteros)
    """
    if not fecha_inicio_contrato:
        return 0
    if as_of <= fecha_inicio_contrato:
        return 0

    meses = _months_between(fecha_inicio_contrato, as_of)
    if meses < 12:
        return 0

    acumulado = Decimal(meses) * Decimal("1.25")
    return int(acumulado)


def _dias_vacaciones_usados(contrato_id: int, *, as_of: date) -> int:
    """
    Consideramos usados SOLO los EMITIDOS (BORRADOR no descuenta).
    Además, sólo contabilizamos comprobantes con fecha_inicio <= as_of.
    """
    q = (
        db.session.query(func.coalesce(func.sum(Vacacion.dias_habiles), 0))
        .filter(Vacacion.contrato_id == contrato_id)
        .filter(Vacacion.estado == "EMITIDO")
        .filter(Vacacion.fecha_inicio <= as_of)
    )
    return int(q.scalar() or 0)


def _get_saldo_contrato(
    contrato_id: int,
    *,
    as_of: date | None = None,
    allow_negative: bool = False,
) -> Decimal:
    """
    Saldo = acumulado por antigüedad - usados (emitidos).

    - Por defecto (allow_negative=False): nunca devuelve negativo (clamp a 0).
    - Para casos de vacaciones anticipadas / auditoría (allow_negative=True): permite saldo negativo.
    """
    if as_of is None:
        as_of = date.today()

    contrato = Contrato.query.get(contrato_id)
    if not contrato:
        return Decimal("0")

    acumulado = _dias_vacaciones_acumulados(contrato.fecha_inicio, as_of)
    usados = _dias_vacaciones_usados(contrato_id, as_of=as_of)

    saldo = Decimal(acumulado - usados)

    if (saldo < 0) and (not allow_negative):
        return Decimal("0")

    return saldo


def _next_corr_contrato(contrato_id: int) -> int:
    max_corr = db.session.query(func.coalesce(func.max(Vacacion.corr_contrato), 0)).filter(
        Vacacion.contrato_id == contrato_id
    ).scalar()
    return int(max_corr or 0) + 1


def _antiguedad_texto(fecha_inicio: date | None, *, as_of: date | None = None) -> str:
    """
    Antigüedad en texto desde fecha_inicio hasta as_of (calendario real):
    - Calcula años/meses/días por diferencias de calendario (no 365/30).
    - Si as_of es None -> usa date.today() (comportamiento UI actual).
    """
    if not fecha_inicio:
        return "-"

    corte = as_of or date.today()
    if corte <= fecha_inicio:
        return "0 días"

    # --- cálculo calendario real ---
    y = corte.year - fecha_inicio.year
    m = corte.month - fecha_inicio.month
    d = corte.day - fecha_inicio.day

    if d < 0:
        # "pedimos prestado" 1 mes del corte
        # días del mes anterior a corte:
        first_of_month = date(corte.year, corte.month, 1)
        last_prev_month = first_of_month - timedelta(days=1)
        d += last_prev_month.day
        m -= 1

    if m < 0:
        m += 12
        y -= 1

    # Sanitizar por si acaso
    y = max(y, 0)
    m = max(m, 0)
    d = max(d, 0)

    # --- armar texto ---
    parts: list[str] = []
    if y > 0:
        parts.append(f"{y} año{'s' if y != 1 else ''}")
    if m > 0:
        parts.append(f"{m} mes{'es' if m != 1 else ''}")

    # Siempre incluimos días (como pediste), incluso si es 0,
    # para que quede completo tipo “X años, Y meses y Z días”.
    parts.append(f"{d} día{'s' if d != 1 else ''}")

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return " y ".join(parts)
    return ", ".join(parts[:-1]) + " y " + parts[-1]




def _can_emit(v: Vacacion) -> bool:
    return v.estado == "BORRADOR"


def _can_anular(v: Vacacion) -> bool:
    return v.estado == "EMITIDO"


def _get_template_path() -> Path:
    return Path(current_app.root_path) / "document_templates" / "solicitudes" / "vacaciones.docx"


def _build_placeholders(v: Vacacion) -> dict[str, str]:
    contrato = v.contrato
    if not contrato or not contrato.trabajador:
        raise ValueError("Vacación sin contrato/trabajador asociado.")

    t = contrato.trabajador
    emp = contrato.empleador
    obra = contrato.obra

    emp_nombre = (emp.razon_social if emp else "-")
    emp_rut = (emp.rut if emp and emp.rut else "-")
    obra_nombre = (obra.nombre if obra else "-")

    fecha_ingreso = contrato.fecha_inicio

    fecha_ingreso_larga = (
        fecha_larga_es(fecha_ingreso)
        if fecha_ingreso
        else "-"
    )

    # ✅ CLAVE: antigüedad a la FECHA DE EMISIÓN del comprobante (no “hoy”)
    antiguedad_doc = _antiguedad_texto(fecha_ingreso, as_of=v.fecha_emision)

    return {
        "{{EMPLEADOR_RAZON_SOCIAL}}": emp_nombre,
        "{{EMPLEADOR_RUT}}": _format_rut_con_puntos(emp_rut),
        "{{OBRA_NOMBRE}}": obra_nombre,
        "{{FECHA_EMISION_LARGA}}": fecha_larga_es(v.fecha_emision),

        "{{TRABAJADOR_NOMBRES}}": (t.nombres or "").strip(),
        "{{TRABAJADOR_AP_PATERNO}}": (t.ap_paterno or "").strip(),
        "{{TRABAJADOR_AP_MATERNO}}": (t.ap_materno or "").strip(),
        "{{TRABAJADOR_RUT}}": _format_rut_con_puntos(t.rut_completo),

        "{{CONTRATO_FECHA_INGRESO}}": fecha_ingreso_larga,
        "{{ANTIGUEDAD_TEXTO}}": antiguedad_doc,

        "{{VAC_ID}}": str(v.id),
        "{{VAC_CORR}}": str(v.corr_contrato),
        "{{VAC_INICIO_LARGA}}": fecha_larga_es(v.fecha_inicio),
        "{{VAC_TERMINO_LARGA}}": fecha_larga_es(v.fecha_termino),
        "{{VAC_DIAS_HABILES}}": str(int(v.dias_habiles or 0)),
        "{{VAC_SALDO_PREV}}": str(v.saldo_prev),
        "{{VAC_SALDO_POST}}": str(v.saldo_post),
        "{{VAC_RETORNO_LARGA}}": fecha_larga_es(v.fecha_retorno),
        "{{VAC_OBS}}": (v.observaciones or "").strip(),
    }



def _centro_costo_from_contrato(contrato: Contrato) -> str:
    obra = contrato.obra
    if obra is None:
        return "SIN_NOMBRE"
    cc = (obra.centro_costo or "").strip()
    if cc:
        return cc
    cod = (obra.codigo or "").strip()
    return cod or "SIN_NOMBRE"


def _safe_filename_part(value: str | None, *, max_len: int = 120) -> str:
    """Normaliza partes de nombre de archivo para Nextcloud/LibreOffice."""
    text = (value or "").strip() or "SIN_NOMBRE"
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9._ -]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-")
    if not text:
        text = "SIN_NOMBRE"
    return text[:max_len].strip(" ._-") or "SIN_NOMBRE"


def _vacaciones_filename_base(v: Vacacion, contrato: Contrato) -> str:
    t = contrato.trabajador
    trabajador_nombre = " ".join(
        p for p in [getattr(t, "ap_paterno", ""), getattr(t, "ap_materno", ""), getattr(t, "nombres", "")] if p
    )
    trabajador_nombre = _safe_filename_part(trabajador_nombre, max_len=90)
    return _safe_filename_part(
        f"{v.fecha_emision.isoformat()} Comp Vacaciones - {trabajador_nombre} - Nro {v.corr_contrato}",
        max_len=160,
    )


# ==========================
# Views
# ==========================

@bp.get("/")
@login_required
def index():
    """
    Listado principal: contratos vigentes con saldo actual + filtros/orden.
    """
    from ...models import Trabajador  # 👈 asegúrate que exista import real en tu archivo si lo prefieres arriba

    cc = (request.args.get("cc") or "").strip()
    emp = (request.args.get("emp") or "").strip()  # id empleador
    derecho = (request.args.get("derecho") or "SI").strip().upper()  # default SI
    orden = (request.args.get("orden") or "saldo_desc").strip().lower()
    q = (request.args.get("q") or "").strip()

    # Base query (solo vigentes)
    q_contratos = (
        db.session.query(Contrato)
        .filter(Contrato.estado_contrato == "VIGENTE")
    )

    # Filtro empresa
    if emp:
        try:
            emp_id = int(emp)
            q_contratos = q_contratos.filter(Contrato.empleador_id == emp_id)
        except Exception:
            pass

    # Búsqueda (Trabajador: nombres/apellidos y RUT)
    if q:
        q_norm = q.strip()
        like = f"%{q_norm}%"

        # Normalizamos para búsquedas tipo RUT:
        # "12.345.678-9" -> "12345678-9"
        rut_norm = (
            q_norm.replace(".", "")
                  .replace(" ", "")
                  .upper()
        )

        # Partes para búsquedas por rut/dv
        rut_digits = rut_norm.replace("-", "")
        rut_only = rut_digits[:-1] if (len(rut_digits) >= 2 and rut_digits[-1].isalnum()) else rut_digits
        dv_only = rut_digits[-1] if (len(rut_digits) >= 2 and rut_digits[-1].isalnum()) else ""

        # Construimos un "rut completo" a nivel SQL: rut + '-' + dv
        rut_completo_sql = db.func.concat(
            db.func.coalesce(Trabajador.rut, ""),
            "-",
            db.func.coalesce(db.func.upper(Trabajador.dv), "")
        )

        # y una versión "rut+dv" sin guion para que matchee "123456789"
        rut_sin_guion_sql = db.func.concat(
            db.func.coalesce(Trabajador.rut, ""),
            db.func.coalesce(db.func.upper(Trabajador.dv), "")
        )

        q_contratos = (
            q_contratos
            .join(Contrato.trabajador)
            .filter(
                db.or_(
                    # Texto libre (nombre/apellidos)
                    Trabajador.nombres.ilike(like),
                    Trabajador.ap_paterno.ilike(like),
                    Trabajador.ap_materno.ilike(like),

                    # RUT tal cual (columna rut) - por si el usuario busca solo dígitos
                    Trabajador.rut.ilike(f"%{rut_only}%"),

                    # RUT completo con guion (rut-dv)
                    rut_completo_sql.ilike(f"%{rut_norm}%"),

                    # RUT completo sin guion (rutdv)
                    rut_sin_guion_sql.ilike(f"%{rut_norm.replace('-', '')}%"),

                    # DV suelta (si alguien escribe solo "K" o "9", apoya)
                    db.func.upper(Trabajador.dv).ilike(f"%{dv_only}%") if dv_only else db.text("1=0"),
                )
            )
        )

    contratos = q_contratos.order_by(Contrato.id.desc()).all()

    as_of = date.today()

    data = []
    for c in contratos:
        saldo = _get_saldo_contrato(c.id, as_of=as_of)

        # Centro de costo (para mostrar y filtrar)
        centro_costo = ""
        if c.obra:
            centro_costo = (c.obra.centro_costo or "").strip() or (c.obra.codigo or "").strip()

        # Derecho: regla MVP 12 meses desde fecha_inicio
        tiene_derecho = False
        if c.fecha_inicio:
            tiene_derecho = (date.today() >= (c.fecha_inicio + timedelta(days=365)))

        # Filtrar CC (aplicado aquí por fallback cc/código)
        if cc and centro_costo != cc:
            continue

        # Filtrar derecho
        if derecho == "SI" and not tiene_derecho:
            continue
        if derecho == "NO" and tiene_derecho:
            continue

        dias_antig = (date.today() - c.fecha_inicio).days if c.fecha_inicio else 0

        data.append({
            "contrato": c,
            "saldo": saldo,
            "tiene_derecho": tiene_derecho,
            "antiguedad": _antiguedad_texto(c.fecha_inicio),
            "centro_costo": centro_costo,
            "_dias_antig": dias_antig,
        })

    # Orden
    if orden == "saldo_asc":
        data.sort(key=lambda r: (r["saldo"], r["contrato"].id))
    elif orden == "antig_desc":
        data.sort(key=lambda r: (r["_dias_antig"], r["contrato"].id), reverse=True)
    elif orden == "antig_asc":
        data.sort(key=lambda r: (r["_dias_antig"], r["contrato"].id))
    elif orden == "contrato_asc":
        data.sort(key=lambda r: r["contrato"].id)
    elif orden == "contrato_desc":
        data.sort(key=lambda r: r["contrato"].id, reverse=True)
    else:
        data.sort(key=lambda r: (r["saldo"], r["contrato"].id), reverse=True)  # saldo_desc default

    # Dropdowns: centros de costo / empresas (desde resultados ya filtrados)
    centros_costo = sorted({r["centro_costo"] for r in data if r["centro_costo"]})

    empresas_map = {}
    for r in data:
        c = r["contrato"]
        if c.empleador:
            empresas_map[c.empleador.id] = c.empleador
    empresas = sorted(empresas_map.values(), key=lambda e: (e.razon_social or "").lower())

    # Resumen KPI
    total = len(data)
    derecho_si = sum(1 for r in data if r["tiene_derecho"])
    saldo_total = sum((r["saldo"] for r in data), Decimal(0))

    return render_template(
        "vacaciones/index.html",
        data=data,
        centros_costo=centros_costo,
        empresas=empresas,
        filtros={"cc": cc, "emp": emp, "derecho": derecho, "orden": orden, "q": q},
        resumen={"total": total, "derecho_si": derecho_si, "saldo_total": saldo_total},
    )

@bp.get("/contrato/<int:contrato_id>")
@login_required
def contrato_detalle(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)

    if contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    as_of = date.today()

    acumulado = _dias_vacaciones_acumulados(
        contrato.fecha_inicio,
        as_of
    )

    usados = _dias_vacaciones_usados(
        contrato.id,
        as_of=as_of
    )

    saldo = _get_saldo_contrato(
        contrato.id,
        as_of=as_of,
        allow_negative=True
    )

    vacaciones = (
        Vacacion.query
        .filter(Vacacion.contrato_id == contrato.id)
        .order_by(Vacacion.fecha_emision.desc(), Vacacion.id.desc())
        .all()
    )

    return render_template(
        "vacaciones/contrato_detalle.html",
        contrato=contrato,
        saldo=saldo,
        acumulado=acumulado,
        usados=usados,
        vacaciones=vacaciones,
        antiguedad=_antiguedad_texto(contrato.fecha_inicio),
    )



@bp.get("/nuevo/<int:contrato_id>")
@login_required
def nuevo(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)
    if contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    fecha_emision = date.today()
    saldo = _get_saldo_contrato(contrato.id, as_of=fecha_emision)
    corr = _next_corr_contrato(contrato.id)

    hoy = date.today()
    start = date(hoy.year - 2, 1, 1)
    end = date(hoy.year + 2, 12, 31)
    feriados_rows = (
        db.session.query(Feriado.fecha)
        .filter(Feriado.fecha >= start)
        .filter(Feriado.fecha <= end)
        .order_by(Feriado.fecha.asc())
        .all()
    )
    feriados_list = [r[0].isoformat() for r in feriados_rows]

    return render_template(
        "vacaciones/form.html",
        modo="nuevo",
        contrato=contrato,
        saldo=saldo,
        corr=corr,
        vac=None,
        antiguedad=_antiguedad_texto(contrato.fecha_inicio),
        fecha_emision_default=fecha_emision.isoformat(),
        feriados=feriados_list,
    )


@bp.post("/nuevo/<int:contrato_id>")
@login_required
def nuevo_post(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)
    if contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    # ✅ fecha_emision viene del form (si no viene, usamos hoy)
    fecha_emision = _parse_date(request.form.get("fecha_emision")) or date.today()

    fecha_inicio = _parse_date(request.form.get("fecha_inicio"))
    fecha_termino = _parse_date(request.form.get("fecha_termino"))
    observaciones = (request.form.get("observaciones") or "").strip()

    # ==========================
    # Vacaciones anticipadas (BORRADOR)
    # ==========================
    anticipo = (request.form.get("anticipo") or "").strip().upper() in {"1", "SI", "TRUE", "ON"}

    dias_habiles_raw = (request.form.get("dias_habiles") or "").strip()
    dias_habiles_input = None
    if dias_habiles_raw:
        try:
            dias_habiles_input = int(dias_habiles_raw)
        except Exception:
            dias_habiles_input = None

    if not fecha_inicio:
        flash("Debes indicar fecha de inicio.", "danger")
        return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

    rango_end = fecha_termino or (fecha_inicio + timedelta(days=365))
    feriados = _feriados_set_between(fecha_inicio, rango_end)

    # ==========================
    # Modo A: días -> calcula término (saltando feriados)
    # ==========================
    if dias_habiles_input is not None:
        if dias_habiles_input < 1:
            flash("Los días hábiles deben ser un número entero mayor o igual a 1.", "danger")
            return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

        cur = fecha_inicio
        counted = 0
        while True:
            if not _is_non_working(cur, feriados):
                counted += 1
            if counted >= dias_habiles_input:
                fecha_termino = cur
                break
            cur += timedelta(days=1)

        dias_habiles = dias_habiles_input
        feriados = _feriados_set_between(fecha_inicio, fecha_termino)

    # ==========================
    # Modo B: término -> calcula días (saltando feriados)
    # ==========================
    else:
        if not fecha_termino:
            flash("Debes indicar fecha de término o la cantidad de días hábiles.", "danger")
            return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

        if fecha_termino < fecha_inicio:
            flash("La fecha de término no puede ser anterior a la fecha de inicio.", "danger")
            return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

        feriados = _feriados_set_between(fecha_inicio, fecha_termino)
        dias_habiles = _count_business_days(fecha_inicio, fecha_termino, feriados=feriados)

    if not fecha_termino or fecha_termino < fecha_inicio or int(dias_habiles or 0) < 1:
        flash("No fue posible determinar correctamente el rango de vacaciones.", "danger")
        return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

    # 👇 Incluimos feriados posteriores al término para calcular retorno correctamente
    feriados_retorno = _feriados_set_between(fecha_inicio, fecha_termino + timedelta(days=30))
    fecha_retorno = _calc_retorno(fecha_termino, feriados=feriados_retorno)

    # ✅ saldo a fecha_emision
    #    OJO: aquí queremos permitir que el BORRADOR quede con saldo negativo si es anticipo (ADMIN).
    saldo_prev = _get_saldo_contrato(
        contrato.id,
        as_of=fecha_emision,
        allow_negative=anticipo,  # 👈 clave (ya validamos ADMIN arriba)
    )
    saldo_post = saldo_prev - Decimal(int(dias_habiles))

    if saldo_post < 0 and not anticipo:
        flash(
            f"Saldo insuficiente. Saldo actual: {saldo_prev}. Días solicitados: {int(dias_habiles)}.",
            "danger"
        )
        return redirect(url_for("vacaciones.nuevo", contrato_id=contrato_id))

    if saldo_post < 0 and anticipo:
        flash(
            f"⚠️ BORRADOR con vacaciones anticipadas. El saldo quedará negativo: {saldo_post}.",
            "warning"
        )

    v = Vacacion(
        contrato_id=contrato.id,
        corr_contrato=_next_corr_contrato(contrato.id),
        fecha_emision=fecha_emision,
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
        fecha_retorno=fecha_retorno,
        dias_habiles=int(dias_habiles),
        saldo_prev=saldo_prev,
        saldo_post=saldo_post,
        observaciones=observaciones,
        estado="BORRADOR",
        es_anticipo=bool(anticipo),  # ✅ NUEVO: se persiste el flag
        creado_por_user_id=current_user.id,
    )

    db.session.add(v)
    db.session.commit()

    flash("Comprobante creado en BORRADOR.", "success")
    return redirect(url_for("vacaciones.detalle", vacaciones_id=v.id))


@bp.get("/<int:vacaciones_id>")
@login_required
def detalle(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)

    contrato = v.contrato
    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    return render_template("vacaciones/detalle.html", v=v, contrato=contrato)


@bp.post("/<int:vacaciones_id>/emitir")
@login_required
def emitir(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)
    contrato = v.contrato

    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    if not _can_emit(v):
        flash("Este comprobante no está en estado BORRADOR.", "warning")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    # ==========================
    # Formato (PDF default)
    # ==========================
    formato = (request.form.get("formato") or "PDF").strip().upper()
    if formato not in {"PDF", "DOCX"}:
        formato = "PDF"

    # ==========================
    # Vacaciones anticipadas (FUENTE DE VERDAD: el BORRADOR)
    # ==========================
    anticipo = bool(getattr(v, "es_anticipo", False))

    # ==========================
    # Recalcular días / retorno (con feriados)
    # ==========================
    feriados_periodo = _feriados_set_between(v.fecha_inicio, v.fecha_termino)

    # 👇 Incluimos feriados posteriores al término para calcular retorno correctamente
    feriados_retorno = _feriados_set_between(v.fecha_inicio, v.fecha_termino + timedelta(days=30))

    v.dias_habiles = int(_count_business_days(v.fecha_inicio, v.fecha_termino, feriados=feriados_periodo))
    v.fecha_retorno = _calc_retorno(v.fecha_termino, feriados=feriados_retorno)

    # ✅ saldo al emitir se calcula a fecha_emision del documento
    saldo_prev = _get_saldo_contrato(
        v.contrato_id,
        as_of=v.fecha_emision,
        allow_negative=anticipo,  # 👈 CLAVE
    )
    saldo_post = saldo_prev - Decimal(int(v.dias_habiles or 0))

    if saldo_post < 0 and not anticipo:
        flash(f"Saldo insuficiente para emitir. Saldo actual: {saldo_prev}.", "danger")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    if saldo_post < 0 and anticipo:
        flash(
            f"⚠️ Vacaciones anticipadas autorizadas. El comprobante quedará con saldo negativo: {saldo_post}.",
            "warning"
        )

    v.saldo_prev = saldo_prev
    v.saldo_post = saldo_post

    try:
        template_path = _get_template_path()
        if not template_path.exists():
            flash(f"No se encuentra plantilla: {template_path}", "danger")
            return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

        # ==========================
        # Nombre archivo seguro para LibreOffice / Nextcloud
        # ==========================
        if not contrato or not contrato.trabajador:
            flash("El comprobante no tiene contrato/trabajador asociado correctamente.", "danger")
            return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

        t = contrato.trabajador
        nombre_base = _vacaciones_filename_base(v, contrato)
        docx_name = f"{nombre_base}.docx"
        pdf_name = f"{nombre_base}.pdf"

        # ==========================
        # 1) Generar DOCX en TEMP local
        # ==========================
        tmp_dir = Path(current_app.instance_path) / "tmp_vacaciones"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        tmp_docx = tmp_dir / docx_name

        doc = Document(str(template_path))
        placeholders = _build_placeholders(v)
        replace_placeholders(doc, placeholders)
        doc.save(str(tmp_docx))

        # ==========================
        # 2) Destino Nextcloud
        # ==========================
        nc = get_nc_paths()
        cc = _centro_costo_from_contrato(contrato)

        dest_dir = nc.dir_trabajador(
            centro_costo=cc,
            nombres=t.nombres,
            ap_paterno=t.ap_paterno,
            ap_materno=t.ap_materno or "",
            tipo_doc="VACACIONES",
        )
        ensure_dir(dest_dir)

        # ==========================
        # 3) Emitir según formato
        # ==========================
        if formato == "DOCX":
            dest_docx = dest_dir / docx_name
            safe_write_bytes(dest_docx, tmp_docx.read_bytes())

            rel_docx = dest_docx.relative_to(nc.base()).as_posix()
            v.docx_nombre = docx_name
            v.docx_ruta = f"/{rel_docx}"

        else:
            # PDF (default)
            pdf_path = convert_docx_to_pdf(tmp_docx, tmp_dir)

            # Aseguramos nombre final corporativo
            tmp_pdf = Path(pdf_path)
            if tmp_pdf.name != pdf_name:
                renamed = tmp_dir / pdf_name
                try:
                    tmp_pdf.replace(renamed)
                    tmp_pdf = renamed
                except Exception:
                    tmp_pdf = Path(pdf_path)

            if not tmp_pdf.exists():
                flash("No se pudo generar el PDF de vacaciones. Intenta emitir en formato Word o revisa LibreOffice.", "danger")
                return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

            dest_pdf = dest_dir / pdf_name
            safe_write_bytes(dest_pdf, tmp_pdf.read_bytes())

            rel_pdf = dest_pdf.relative_to(nc.base()).as_posix()
            v.pdf_nombre = pdf_name
            v.pdf_ruta = f"/{rel_pdf}"

    except Exception as exc:
        current_app.logger.exception("Error emitiendo comprobante de vacaciones id=%s", vacaciones_id)
        db.session.rollback()
        flash(f"No se pudo emitir el comprobante de vacaciones: {exc}", "danger")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    # ==========================
    # 4) Movimiento ledger (USO)
    # ==========================
    mov = VacacionMovimiento(
        contrato_id=v.contrato_id,
        tipo="USO",
        fecha=v.fecha_emision,
        dias=Decimal(str(-int(v.dias_habiles or 0))),
        vacaciones_id=v.id,
        detalle=f"Comprobante vacaciones N° {v.corr_contrato}",
        creado_por_user_id=current_user.id,
    )

    v.estado = "EMITIDO"
    db.session.add(mov)
    db.session.commit()

    flash(f"Comprobante emitido ({formato}) y registrado en movimientos.", "success")
    return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))



@bp.post("/<int:vacaciones_id>/anular")
@login_required
def anular(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)
    contrato = v.contrato

    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    if not _can_anular(v):
        flash("Solo se pueden anular comprobantes EMITIDOS.", "warning")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    mov = VacacionMovimiento(
        contrato_id=v.contrato_id,
        tipo="AJUSTE",
        fecha=date.today(),
        dias=Decimal(str(int(v.dias_habiles or 0))),
        vacaciones_id=v.id,
        detalle=f"Anulación comprobante vacaciones N° {v.corr_contrato}",
        creado_por_user_id=current_user.id,
    )

    v.estado = "ANULADO"
    db.session.add(mov)
    db.session.commit()

    flash("Comprobante ANULADO. Se registró ajuste de reversa.", "success")
    return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

@bp.get("/<int:vacaciones_id>/editar")
@login_required
def editar(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)
    contrato = v.contrato

    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    if v.estado != "BORRADOR":
        flash("Solo se pueden editar comprobantes en estado BORRADOR.", "warning")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=v.id))

    # saldo a la fecha de emisión del comprobante
    saldo = _get_saldo_contrato(contrato.id, as_of=v.fecha_emision)

    # feriados para JS (rango amplio)
    hoy = date.today()
    start = date(hoy.year - 2, 1, 1)
    end = date(hoy.year + 2, 12, 31)
    feriados_rows = (
        db.session.query(Feriado.fecha)
        .filter(Feriado.fecha >= start)
        .filter(Feriado.fecha <= end)
        .order_by(Feriado.fecha.asc())
        .all()
    )
    feriados_list = [r[0].isoformat() for r in feriados_rows]

    return render_template(
        "vacaciones/form.html",
        modo="editar",
        contrato=contrato,
        saldo=saldo,
        corr=v.corr_contrato,
        vac=v,
        antiguedad=_antiguedad_texto(contrato.fecha_inicio),
        fecha_emision_default=v.fecha_emision.isoformat(),
        feriados=feriados_list,
    )


@bp.post("/<int:vacaciones_id>/editar")
@login_required
def editar_post(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)
    contrato = v.contrato

    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    if v.estado != "BORRADOR":
        flash("Solo se pueden editar comprobantes en estado BORRADOR.", "warning")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=v.id))

    fecha_emision = _parse_date(request.form.get("fecha_emision")) or date.today()
    fecha_inicio = _parse_date(request.form.get("fecha_inicio"))
    fecha_termino = _parse_date(request.form.get("fecha_termino"))
    observaciones = (request.form.get("observaciones") or "").strip()

    # ==========================
    # Vacaciones anticipadas (BORRADOR)
    # ==========================
    anticipo = (request.form.get("anticipo") or "").strip().upper() in {"1", "SI", "TRUE", "ON"}

    dias_habiles_raw = (request.form.get("dias_habiles") or "").strip()
    dias_habiles_input = None
    if dias_habiles_raw:
        try:
            dias_habiles_input = int(dias_habiles_raw)
        except Exception:
            dias_habiles_input = None

    if not fecha_inicio:
        flash("Debes indicar fecha de inicio.", "danger")
        return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

    rango_end = fecha_termino or (fecha_inicio + timedelta(days=365))
    feriados = _feriados_set_between(fecha_inicio, rango_end)

    # Modo A: días -> calcula término
    if dias_habiles_input is not None:
        if dias_habiles_input < 1:
            flash("Los días hábiles deben ser un número entero mayor o igual a 1.", "danger")
            return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

        cur = fecha_inicio
        counted = 0
        while True:
            if not _is_non_working(cur, feriados):
                counted += 1
            if counted >= dias_habiles_input:
                fecha_termino = cur
                break
            cur += timedelta(days=1)

        dias_habiles = dias_habiles_input
        feriados = _feriados_set_between(fecha_inicio, fecha_termino)

    # Modo B: término -> calcula días
    else:
        if not fecha_termino:
            flash("Debes indicar fecha de término o la cantidad de días hábiles.", "danger")
            return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

        if fecha_termino < fecha_inicio:
            flash("La fecha de término no puede ser anterior a la fecha de inicio.", "danger")
            return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

        feriados = _feriados_set_between(fecha_inicio, fecha_termino)
        dias_habiles = _count_business_days(fecha_inicio, fecha_termino, feriados=feriados)

    if not fecha_termino or fecha_termino < fecha_inicio or int(dias_habiles or 0) < 1:
        flash("No fue posible determinar correctamente el rango de vacaciones.", "danger")
        return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

    feriados_retorno = _feriados_set_between(fecha_inicio, fecha_termino + timedelta(days=30))
    fecha_retorno = _calc_retorno(fecha_termino, feriados=feriados_retorno)

    # ✅ saldo a fecha_emision (permitiendo negativos si anticipo)
    saldo_prev = _get_saldo_contrato(
        contrato.id,
        as_of=fecha_emision,
        allow_negative=anticipo,  # 👈 ya validamos ADMIN arriba
    )
    saldo_post = saldo_prev - Decimal(int(dias_habiles))

    if saldo_post < 0 and not anticipo:
        flash(
            f"Saldo insuficiente. Saldo actual: {saldo_prev}. Días solicitados: {int(dias_habiles)}.",
            "danger"
        )
        return redirect(url_for("vacaciones.editar", vacaciones_id=v.id))

    if saldo_post < 0 and anticipo:
        flash(
            f"⚠️ BORRADOR con vacaciones anticipadas. El saldo quedará negativo: {saldo_post}.",
            "warning"
        )

    # Guardar cambios en el borrador
    v.fecha_emision = fecha_emision
    v.fecha_inicio = fecha_inicio
    v.fecha_termino = fecha_termino
    v.fecha_retorno = fecha_retorno
    v.dias_habiles = int(dias_habiles)
    v.saldo_prev = saldo_prev
    v.saldo_post = saldo_post
    v.observaciones = observaciones
    v.es_anticipo = bool(anticipo)  # ✅ NUEVO: persistimos el flag

    db.session.commit()

    flash("Borrador actualizado.", "success")
    return redirect(url_for("vacaciones.detalle", vacaciones_id=v.id))

@bp.post("/<int:vacaciones_id>/reemitir")
@login_required
def reemitir(vacaciones_id: int):
    v = Vacacion.query.get_or_404(vacaciones_id)
    contrato = v.contrato

    if contrato and contrato.obra_id and not current_user.can_access_obra(contrato.obra_id):
        abort(403)

    if v.estado != "EMITIDO":
        flash("Solo se puede re-emitir un comprobante en estado EMITIDO.", "warning")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    # ✅ Formato (default PDF)
    formato = (request.form.get("formato") or "pdf").strip().lower()
    if formato not in {"pdf", "docx"}:
        formato = "pdf"

    template_path = _get_template_path()
    if not template_path.exists():
        flash(f"No se encuentra plantilla: {template_path}", "danger")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    # Nombre base (mismo estándar)
    t = contrato.trabajador
    nombre_base = _vacaciones_filename_base(v, contrato)
    docx_name = f"{nombre_base}.docx"
    pdf_name = f"{nombre_base}.pdf"

    # ==========================
    # 1) Generar en TEMP
    # ==========================
    tmp_dir = Path(current_app.instance_path) / "tmp_vacaciones"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_docx = tmp_dir / docx_name
    tmp_pdf = tmp_dir / pdf_name  # solo se usará si formato == "pdf"

    doc = Document(str(template_path))
    placeholders = _build_placeholders(v)
    replace_placeholders(doc, placeholders)
    doc.save(str(tmp_docx))

    # Si piden PDF, convertimos (LibreOffice escribe en tmp_dir/<stem>.pdf)
    if formato == "pdf":
        pdf_path = convert_docx_to_pdf(tmp_docx, tmp_dir)

        generated_pdf = Path(pdf_path) if pdf_path else (tmp_dir / (tmp_docx.stem + ".pdf"))
        if not generated_pdf.exists():
            flash("No se pudo generar el PDF (LibreOffice no entregó el archivo esperado).", "danger")
            return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

        # Aseguramos nombre final exacto
        if generated_pdf.name != pdf_name:
            try:
                generated_pdf.replace(tmp_pdf)
                generated_pdf = tmp_pdf
            except Exception:
                # fallback: copiar bytes
                tmp_pdf.write_bytes(generated_pdf.read_bytes())
                generated_pdf = tmp_pdf

    # ==========================
    # 2) Subir/reescribir a Nextcloud FS
    # ==========================
    nc = get_nc_paths()
    cc = _centro_costo_from_contrato(contrato)

    dest_dir = nc.dir_trabajador(
        centro_costo=cc,
        nombres=t.nombres,
        ap_paterno=t.ap_paterno,
        ap_materno=t.ap_materno or "",
        tipo_doc="VACACIONES",
    )
    ensure_dir(dest_dir)

    dest_docx = dest_dir / docx_name
    dest_pdf = dest_dir / pdf_name

    # ==========================
    # 3) Subida estricta según formato
    # ==========================
    if formato == "docx":
        safe_write_bytes(dest_docx, tmp_docx.read_bytes())

        rel_docx = dest_docx.relative_to(nc.base()).as_posix()
        v.docx_nombre = docx_name
        v.docx_ruta = f"/{rel_docx}"

        # NO tocamos PDF (se mantiene si existía)
        db.session.commit()
        flash("Comprobante re-emitido ✅ DOCX regenerado en Nextcloud (sin afectar saldos).", "success")
        return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))

    # formato == "pdf"
    # Subimos SOLO PDF (aunque el DOCX exista en temporal)
    safe_write_bytes(dest_pdf, tmp_pdf.read_bytes())

    rel_pdf = dest_pdf.relative_to(nc.base()).as_posix()
    v.pdf_nombre = pdf_name
    v.pdf_ruta = f"/{rel_pdf}"

    # NO tocamos DOCX (se mantiene si existía)
    db.session.commit()

    flash("Comprobante re-emitido ✅ PDF regenerado en Nextcloud (sin afectar saldos).", "success")
    return redirect(url_for("vacaciones.detalle", vacaciones_id=vacaciones_id))
