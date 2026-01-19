from __future__ import annotations

from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from itertools import groupby
from typing import Iterable

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Trabajador, Contrato, Inasistencia, Obra
from app.utils import parse_date, parse_int
from app.auth.decorators import role_required
from . import bp


# ============================================================
# Catálogo de Motivos (guardar CÓDIGO en DB, mostrar LABEL en UI)
# ============================================================

# Nota: "no_descuenta" es informativo para UI (badge azul).
# "cuenta_art160" define si entra al conteo de causal Art.160 N°3.
MOTIVOS: dict[str, dict] = {
    # --- DÍA COMPLETO ---
    "AUSENCIA_INJUSTIFICADA": {
        "label": "Ausencia injustificada",
        "tipo": "DIA",
        "no_descuenta": False,
        "badge": "bg-danger",
        "cuenta_art160": True,
    },
    "PERMISO_SIN_GOCE": {
        "label": "Permiso sin goce de sueldo",
        "tipo": "DIA",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "PERMISO_CON_GOCE": {
        "label": "Permiso con goce de sueldo",
        "tipo": "DIA",
        "no_descuenta": True,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },
    "LICENCIA_MEDICA": {
        "label": "Licencia médica",
        "tipo": "DIA",
        "no_descuenta": False,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },
    "ACCIDENTE_LABORAL_MUTUAL": {
        "label": "Accidente laboral (Licencia Mutual)",
        "tipo": "DIA",
        "no_descuenta": False,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },
    "JUSTIFICATIVO_MEDICO": {
        "label": "Ausencia con justificativo médico",
        "tipo": "DIA",
        "no_descuenta": False,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },
    "PERMISO_DUELO": {
        "label": "Permiso por duelo",
        "tipo": "DIA",
        "no_descuenta": True,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },

    # --- HORAS / MINUTOS ---
    "ATRASO": {
        "label": "Atraso",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "PERMISO": {
        "label": "Permiso",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "AUSENCIA_MEDIA_JORNADA": {
        "label": "Ausencia media jornada",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "PERMISO_MEDIA_JORNADA": {
        "label": "Permiso media jornada",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "PERMISO_MEDICO": {
        "label": "Permiso médico",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "PERMISO_TRAMITES": {
        "label": "Permiso trámites personales",
        "tipo": "HORAS",
        "no_descuenta": False,
        "badge": "bg-secondary",
        "cuenta_art160": False,
    },
    "EXAMEN_PREOCUPACIONAL": {
        "label": "Permiso por examen preocupacional",
        "tipo": "HORAS",
        "no_descuenta": True,
        "badge": "bg-primary",
        "cuenta_art160": False,
    },
}


def _motivos_por_tipo(tipo: str) -> list[tuple[str, dict]]:
    tipo = (tipo or "").upper().strip()
    return [(k, v) for k, v in MOTIVOS.items() if v.get("tipo") == tipo]


def _motivo_meta(codigo: str | None) -> dict | None:
    if not codigo:
        return None
    return MOTIVOS.get(codigo)


# ============================================================
# Helpers
# ============================================================
def _minutos_desde_hhmm(hhmm: str | None) -> int | None:
    """
    Convierte 'HH:MM' a minutos totales.
    Retorna None si inválido o 00:00.
    """
    if not hhmm:
        return None
    try:
        h_str, m_str = hhmm.strip().split(":")
        h = int(h_str)
        m = int(m_str)
        if h < 0 or m < 0 or m > 59:
            return None
        total = h * 60 + m
        return total if total > 0 else None
    except Exception:
        return None


def _contrato_vigente_para(trabajador_id: int, fecha_ref: date) -> Contrato | None:
    """
    Contrato vigente para una fecha (no solo hoy).
    """
    return (
        Contrato.query
        .filter(
            Contrato.trabajador_id == trabajador_id,
            Contrato.fecha_inicio <= fecha_ref,
            or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= fecha_ref),
        )
        .order_by(Contrato.fecha_inicio.desc())
        .first()
    )


def _trabajadores_para_selector():
    ap_pat = func.coalesce(func.nullif(func.trim(Trabajador.ap_paterno), ""), "")
    ap_mat = func.coalesce(func.nullif(func.trim(Trabajador.ap_materno), ""), "")
    noms = func.coalesce(func.nullif(func.trim(Trabajador.nombres), ""), "")

    return (
        Trabajador.query
        .order_by(
            (ap_pat == "").asc(),
            ap_pat.asc(),
            ap_mat.asc(),
            noms.asc(),
            Trabajador.id.asc(),
        )
        .all()
    )


def _centros_costo():
    """
    Lista de centros de costo únicos (obras.centro_costo), ordenados.
    Ignora null / vacío.
    """
    rows = (
        db.session.query(func.trim(Obra.centro_costo))
        .filter(Obra.centro_costo.isnot(None))
        .filter(func.trim(Obra.centro_costo) != "")
        .distinct()
        .order_by(func.trim(Obra.centro_costo).asc())
        .all()
    )
    return [r[0] for r in rows if r and r[0]]


def _fmt_hhmm(minutos: int | None) -> str:
    if not minutos:
        return ""
    hh = minutos // 60
    mm = minutos % 60
    return f"{hh:02d}:{mm:02d}"


def _safe_next(url: str | None) -> str | None:
    """
    Permite redirecciones solo a rutas relativas internas.
    Evita open-redirect (seguridad básica).
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("/") and not url.startswith("//"):
        return url
    return None


def _current_full_path() -> str:
    """
    URL actual con querystring para persistir filtros.
    Evita el caso '...?' cuando no hay query.
    """
    full = request.full_path  # e.g. "/inasistencias/?cc=QUINTERO&mes=2026-01"
    return full[:-1] if full.endswith("?") else full


def _mes_bounds(fecha: date) -> tuple[date, date]:
    desde = date(fecha.year, fecha.month, 1)
    if fecha.month == 12:
        hasta = date(fecha.year + 1, 1, 1)
    else:
        hasta = date(fecha.year, fecha.month + 1, 1)
    return desde, hasta


def _evaluar_causal_art160_n3(
    trabajador_id: int,
    fecha_ref: date,
    fechas_extra: Iterable[date] = (),
) -> list[str]:
    """
    Evalúa causal Art. 160 N°3 (no concurrencia):
    - 2 días seguidos en el mes
    - 2 lunes en el mes
    - 3 días en el mes
    Considera solo inasistencias tipo DIA y motivo AUSENCIA_INJUSTIFICADA.
    """
    desde, hasta = _mes_bounds(fecha_ref)

    rows = (
        db.session.query(Inasistencia.fecha)
        .filter(
            Inasistencia.trabajador_id == trabajador_id,
            Inasistencia.fecha >= desde,
            Inasistencia.fecha < hasta,
            Inasistencia.tipo == "DIA",
            Inasistencia.motivo == "AUSENCIA_INJUSTIFICADA",
        )
        .all()
    )

    fechas: set[date] = {r[0] for r in rows if r and r[0]}
    for f in fechas_extra:
        if f and desde <= f < hasta:
            fechas.add(f)

    if not fechas:
        return []

    fechas_ord = sorted(fechas)

    # total de 3 días
    alertas: list[str] = []
    if len(fechas_ord) >= 3:
        alertas.append("3 días ausentes en el mes")

    # 2 lunes en el mes
    lunes = sum(1 for f in fechas_ord if f.weekday() == 0)
    if lunes >= 2:
        alertas.append("2 días lunes ausentes en el mes")

    # 2 días seguidos
    seguidos = False
    for i in range(1, len(fechas_ord)):
        if (fechas_ord[i] - fechas_ord[i - 1]).days == 1:
            seguidos = True
            break
    if seguidos:
        alertas.append("2 días seguidos ausentes en el mes")

    return alertas


def _flash_alerta_art160(trabajador_id: int, fecha_ref: date, fechas_extra: Iterable[date] = ()):
    """
    Dispara flash si hay causal Art.160 N°3.
    """
    alertas = _evaluar_causal_art160_n3(trabajador_id, fecha_ref, fechas_extra=fechas_extra)
    if not alertas:
        return

    t = Trabajador.query.get(trabajador_id)
    nombre = "Trabajador"
    if t:
        nombre = f"{t.ap_paterno} {t.ap_materno} {t.nombres}".strip()

    detalle = " / ".join(alertas)
    flash(
        f"Aviso RRHH: {nombre} registra {detalle}. "
        "Esto puede configurar causal de término por 'No concurrencia' (Art. 160 N°3, Código del Trabajo). "
        "Revisar antecedentes y respaldo antes de desvincular.",
        "warning",
    )

def _format_rut(body: str | int | None, dv: str | None) -> str:
    """
    Formatea RUT chileno: 12.345.678-9
    - body: cuerpo (solo números, puede venir con puntos/guion/espacios)
    - dv: dígito verificador (0-9 / K)
    """
    if body is None:
        return ""

    body_str = str(body).strip().replace(".", "").replace("-", "").replace(" ", "")
    dv_str = (dv or "").strip().upper()

    if not body_str:
        return ""

    # Solo dejamos dígitos en cuerpo
    body_digits = "".join(ch for ch in body_str if ch.isdigit())
    if not body_digits:
        return ""

    # Miles con puntos
    body_fmt = f"{int(body_digits):,}".replace(",", ".")

    return f"{body_fmt}-{dv_str}" if dv_str else body_fmt


# ---------------------------
# Listado
# ---------------------------
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR")
def listado():
    trabajador_id = parse_int(request.args.get("trabajador_id"))
    cc = (request.args.get("cc") or "").strip()

    tz_cl = ZoneInfo("America/Santiago")
    hoy = datetime.now(tz_cl).date()
    mes_default = hoy.strftime("%Y-%m")
    mes = (request.args.get("mes") or "").strip() or mes_default

    q = (
        Inasistencia.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == Trabajador.obra_id)
        .options(joinedload(Inasistencia.trabajador).joinedload(Trabajador.obra))
    )

    if trabajador_id:
        q = q.filter(Inasistencia.trabajador_id == trabajador_id)

    if cc:
        q = q.filter(func.trim(Obra.centro_costo) == cc)

    if mes:
        try:
            y_str, m_str = mes.split("-")
            y = int(y_str)
            m = int(m_str)
            desde = date(y, m, 1)
            hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            q = q.filter(Inasistencia.fecha >= desde, Inasistencia.fecha < hasta)
        except Exception:
            flash("Mes inválido. Usa formato YYYY-MM.", "warning")

    items = q.order_by(Inasistencia.fecha.desc(), Inasistencia.id.desc()).limit(300).all()
    dias = [(f, list(g)) for f, g in groupby(items, key=lambda x: x.fecha)]

    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    return render_template(
        "inasistencias/listado.html",
        items=items,
        dias=dias,
        trabajadores=trabajadores,
        centros_costo=centros_costo,
        trabajador_id=trabajador_id,
        cc=cc,
        mes=mes,
        mes_default=mes_default,
        fmt_hhmm=_fmt_hhmm,
        next_url=_current_full_path(),
        hoy=hoy,
        motivo_meta=MOTIVOS,  # ✅ para badges/labels en listado
    )


# ---------------------------
# Nuevo (con rango)
# ---------------------------
@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def nuevo():
    trabajadores = _trabajadores_para_selector()

    tz_cl = ZoneInfo("America/Santiago")
    hoy = datetime.now(tz_cl).date()

    # Preselección opcional desde querystring (?trabajador_id=123)
    pre_trabajador_id = parse_int(request.args.get("trabajador_id"))

    pre_trabajador_label = ""
    if pre_trabajador_id:
        t = Trabajador.query.get(pre_trabajador_id)
        if t:
            pre_trabajador_label = f"{t.id} - {t.ap_paterno} {t.ap_materno} {t.nombres} · RUT: {t.rut}"

    if request.method == "POST":
        trabajador_id = parse_int(request.form.get("trabajador_id"))

        fecha_desde = parse_date(request.form.get("fecha_desde"))
        fecha_hasta = parse_date(request.form.get("fecha_hasta")) or fecha_desde

        tipo = (request.form.get("tipo") or "DIA").upper().strip()
        motivo = (request.form.get("motivo") or "").strip()
        observacion = (request.form.get("observacion") or "").strip() or None
        hhmm = (request.form.get("hhmm") or "").strip()

        if not trabajador_id:
            flash("Debes seleccionar un trabajador.", "error")
            return redirect(url_for("inasistencias.nuevo"))

        if not fecha_desde:
            flash("Debes indicar la fecha 'Desde'.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        if not fecha_hasta:
            fecha_hasta = fecha_desde

        if fecha_hasta < fecha_desde:
            flash("La fecha 'Hasta' no puede ser anterior a 'Desde'.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        dias_rango = (fecha_hasta - fecha_desde).days + 1
        if dias_rango > 90:
            flash("Rango demasiado amplio (máx. 90 días).", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        if tipo not in ("DIA", "HORAS"):
            flash("Tipo inválido.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        # Validar motivo según catálogo
        meta = _motivo_meta(motivo)
        if not meta or meta.get("tipo") != tipo:
            flash("Debes seleccionar un motivo válido para el tipo indicado.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        minutos = None
        if tipo == "HORAS":
            minutos = _minutos_desde_hhmm(hhmm)
            if not minutos:
                flash("Para 'Horas', debes indicar un tiempo válido (HH:MM) mayor a 00:00.", "error")
                return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        creadas, omitidas = 0, 0
        fechas_creadas: list[date] = []

        fecha_iter = fecha_desde
        for _ in range(dias_rango):
            existe = (
                Inasistencia.query
                .filter_by(trabajador_id=trabajador_id, fecha=fecha_iter, tipo=tipo)
                .first()
            )
            if existe:
                omitidas += 1
                fecha_iter += timedelta(days=1)
                continue

            contrato = _contrato_vigente_para(trabajador_id, fecha_iter)
            contrato_id = contrato.id if contrato else None

            db.session.add(Inasistencia(
                trabajador_id=trabajador_id,
                contrato_id=contrato_id,
                fecha=fecha_iter,
                tipo=tipo,
                minutos_ausentes=minutos,
                motivo=motivo,  # ✅ guardar CÓDIGO
                observacion=observacion,
                creado_por_user_id=getattr(current_user, "id", None),
            ))
            creadas += 1
            fechas_creadas.append(fecha_iter)
            fecha_iter += timedelta(days=1)

        db.session.commit()

        if not (creadas > 0):
            flash("No se creó ningún registro (probablemente eran duplicados).", "warning")
        else:
            flash(f"Inasistencias registradas. Creadas: {creadas} · Omitidas: {omitidas}", "success")

        # ✅ Alerta Art.160 N°3 (solo si corresponde: día + ausencia injustificada)
        if tipo == "DIA" and motivo == "AUSENCIA_INJUSTIFICADA" and fechas_creadas:
            # evaluar por cada mes involucrado (sin duplicar flashes por el mismo mes)
            meses: set[tuple[int, int]] = {(f.year, f.month) for f in fechas_creadas}
            for (y, m) in sorted(meses):
                ref = date(y, m, 1)
                _flash_alerta_art160(trabajador_id, ref, fechas_extra=fechas_creadas)

        return redirect(url_for("inasistencias.listado", trabajador_id=trabajador_id))

    return render_template(
        "inasistencias/nuevo.html",
        trabajadores=trabajadores,
        hoy=hoy,
        pre_trabajador_id=pre_trabajador_id,
        pre_trabajador_label=pre_trabajador_label,
        motivos_dia=_motivos_por_tipo("DIA"),
        motivos_horas=_motivos_por_tipo("HORAS"),
    )


# ---------------------------
# Editar
# ---------------------------
@bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def editar(item_id: int):
    item = Inasistencia.query.get_or_404(item_id)
    trabajadores = _trabajadores_para_selector()

    next_url = _safe_next(request.args.get("next")) or _safe_next(request.form.get("next"))

    if request.method == "POST":
        fecha = parse_date(request.form.get("fecha"))
        tipo = (request.form.get("tipo") or "DIA").upper().strip()
        motivo = (request.form.get("motivo") or "").strip()
        observacion = (request.form.get("observacion") or "").strip() or None
        hhmm = (request.form.get("hhmm") or "").strip()

        if not fecha:
            flash("Debes indicar la fecha.", "error")
            return redirect(url_for("inasistencias.editar", item_id=item_id, next=next_url) if next_url else url_for("inasistencias.editar", item_id=item_id))

        if tipo not in ("DIA", "HORAS"):
            flash("Tipo inválido.", "error")
            return redirect(url_for("inasistencias.editar", item_id=item_id, next=next_url) if next_url else url_for("inasistencias.editar", item_id=item_id))

        meta = _motivo_meta(motivo)
        if not meta or meta.get("tipo") != tipo:
            flash("Debes seleccionar un motivo válido para el tipo indicado.", "error")
            return redirect(url_for("inasistencias.editar", item_id=item_id, next=next_url) if next_url else url_for("inasistencias.editar", item_id=item_id))

        minutos = None
        if tipo == "HORAS":
            minutos = _minutos_desde_hhmm(hhmm)
            if not minutos:
                flash("Tiempo inválido (HH:MM).", "error")
                return redirect(url_for("inasistencias.editar", item_id=item_id, next=next_url) if next_url else url_for("inasistencias.editar", item_id=item_id))

        contrato = _contrato_vigente_para(item.trabajador_id, fecha)
        contrato_id = contrato.id if contrato else None
        if not contrato:
            flash(
                "Aviso: Inasistencia quedará SIN contrato asociado (no existe contrato vigente para esa fecha).",
                "warning",
            )

        item.fecha = fecha
        item.tipo = tipo
        item.minutos_ausentes = minutos
        item.motivo = motivo  # ✅ guardar CÓDIGO
        item.observacion = observacion
        item.contrato_id = contrato_id

        db.session.commit()
        flash("Inasistencia actualizada.", "success")

        # ✅ Alerta Art.160 N°3 si quedó como injustificada día
        if item.tipo == "DIA" and item.motivo == "AUSENCIA_INJUSTIFICADA":
            _flash_alerta_art160(item.trabajador_id, item.fecha, fechas_extra=[item.fecha])

        if next_url:
            return redirect(next_url)
        return redirect(url_for("inasistencias.listado", trabajador_id=item.trabajador_id))

    return render_template(
        "inasistencias/editar.html",
        item=item,
        trabajadores=trabajadores,
        hhmm=_fmt_hhmm(item.minutos_ausentes),
        next_url=next_url,
        motivos_dia=_motivos_por_tipo("DIA"),
        motivos_horas=_motivos_por_tipo("HORAS"),
    )


# ---------------------------
# Eliminar
# ---------------------------
@bp.post("/<int:item_id>/eliminar")
@login_required
@role_required("ADMIN", "OPERADOR")
def eliminar(item_id: int):
    item = Inasistencia.query.get_or_404(item_id)
    trabajador_id = item.trabajador_id

    next_url = _safe_next(request.args.get("next")) or _safe_next(request.form.get("next"))

    db.session.delete(item)
    db.session.commit()

    flash("Inasistencia eliminada.", "success")

    if next_url:
        return redirect(next_url)
    return redirect(url_for("inasistencias.listado", trabajador_id=trabajador_id))


# ---------------------------
# Revisión remuneraciones
# ---------------------------
@bp.route("/revision", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def revision():
    cc = (request.args.get("cc") or "").strip()

    tz_cl = ZoneInfo("America/Santiago")
    hoy = datetime.now(tz_cl).date()
    mes_default = hoy.strftime("%Y-%m")
    mes = (request.args.get("mes") or "").strip() or mes_default

    estado = (request.args.get("estado") or "").strip() or "pendientes"
    if estado not in ("pendientes", "procesadas", "todas"):
        estado = "pendientes"

    q = (
        Inasistencia.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == Trabajador.obra_id)
        .options(joinedload(Inasistencia.trabajador).joinedload(Trabajador.obra))
    )

    if cc:
        q = q.filter(func.trim(Obra.centro_costo) == cc)

    # Filtro por mes
    if mes:
        try:
            y_str, m_str = mes.split("-")
            y = int(y_str)
            m = int(m_str)
            desde = date(y, m, 1)
            hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            q = q.filter(Inasistencia.fecha >= desde, Inasistencia.fecha < hasta)
        except Exception:
            flash("Mes inválido. Usa formato YYYY-MM.", "warning")

    # Filtro por estado
    if estado == "pendientes":
        q = q.filter(Inasistencia.procesada.is_(False))
    elif estado == "procesadas":
        q = q.filter(Inasistencia.procesada.is_(True))
    # "todas": sin filtro

    # ---------------------------
    # POST: marcar procesadas
    # ---------------------------
    if request.method == "POST":
        # 1) Botón por trabajador
        trabajador_post = parse_int(request.form.get("trabajador_id"))
        if trabajador_post:
            q_upd = Inasistencia.query.filter(
                Inasistencia.trabajador_id == trabajador_post,
                Inasistencia.procesada.is_(False),
            )

            # Reaplicar filtros (cc/mes) al update para respetar el contexto de revisión
            if cc:
                q_upd = (
                    q_upd.join(Trabajador)
                    .outerjoin(Obra, Obra.id == Trabajador.obra_id)
                    .filter(func.trim(Obra.centro_costo) == cc)
                )

            if mes:
                try:
                    y_str, m_str = mes.split("-")
                    y = int(y_str)
                    m = int(m_str)
                    desde = date(y, m, 1)
                    hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
                    q_upd = q_upd.filter(Inasistencia.fecha >= desde, Inasistencia.fecha < hasta)
                except Exception:
                    pass

            n = q_upd.update(
                {"procesada": True, "procesada_en": datetime.utcnow()},
                synchronize_session=False,
            )
            db.session.commit()
            flash(f"{n} inasistencias marcadas como procesadas para este trabajador.", "success")

            return redirect(url_for("inasistencias.revision", cc=cc, mes=mes, estado=estado))

        # 2) Checkboxes individuales
        ids = request.form.getlist("inasistencia_id")
        if ids:
            n = (
                Inasistencia.query
                .filter(Inasistencia.id.in_(ids))
                .filter(Inasistencia.procesada.is_(False))
                .update(
                    {"procesada": True, "procesada_en": datetime.utcnow()},
                    synchronize_session=False,
                )
            )
            db.session.commit()
            flash(f"{n} inasistencias marcadas como procesadas.", "success")

        return redirect(url_for("inasistencias.revision", cc=cc, mes=mes, estado=estado))

    # ---------------------------
    # Orden alfabético garantizado
    # ---------------------------
    items = q.order_by(
        Trabajador.ap_paterno.asc(),
        Trabajador.ap_materno.asc(),
        Trabajador.nombres.asc(),
        Inasistencia.fecha.asc(),
        Inasistencia.id.asc(),
    ).all()

    # Mapa: trabajador_id -> RUT formateado (usa rut + dv)
    rut_fmt_map: dict[int, str] = {}
    for it in items:
        t = it.trabajador
        if not t or not t.id:
            continue
        rut_fmt_map[t.id] = _format_rut(t.rut, t.dv)
    centros_costo = _centros_costo()

    return render_template(
        "inasistencias/revision.html",
        items=items,
        centros_costo=centros_costo,
        cc=cc,
        mes=mes,
        estado=estado,
        fmt_hhmm=_fmt_hhmm,
        motivo_meta=MOTIVOS,  # para badges/labels
        rut_fmt_map=rut_fmt_map,
    )

