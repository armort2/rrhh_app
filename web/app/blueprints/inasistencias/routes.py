from __future__ import annotations

from datetime import date, timedelta, datetime

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Trabajador, Contrato, Inasistencia, Obra
from app.utils import parse_date, parse_int
from app.auth.decorators import role_required
from . import bp


# ---------------------------
# Helpers
# ---------------------------
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


# ---------------------------
# Listado
# ---------------------------
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR")
def listado():
    trabajador_id = parse_int(request.args.get("trabajador_id"))
    cc = (request.args.get("cc") or "").strip()  # Centro de costo (texto)
    mes = (request.args.get("mes") or "").strip()  # YYYY-MM

    q = (
        Inasistencia.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == Trabajador.obra_id)  # robusto ante obra_id NULL
        .options(
            joinedload(Inasistencia.trabajador).joinedload(Trabajador.obra)
        )
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
    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    return render_template(
        "inasistencias/listado.html",
        items=items,
        trabajadores=trabajadores,
        centros_costo=centros_costo,
        trabajador_id=trabajador_id,
        cc=cc,
        mes=mes,
        fmt_hhmm=_fmt_hhmm,
        next_url=_current_full_path(),
    )


# ---------------------------
# Nuevo (con rango)
# ---------------------------
@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def nuevo():
    trabajadores = _trabajadores_para_selector()

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

        dias = (fecha_hasta - fecha_desde).days + 1
        if dias > 90:
            flash("Rango demasiado amplio (máx. 90 días).", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        if tipo not in ("DIA", "HORAS"):
            flash("Tipo inválido.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        if not motivo:
            flash("Debes indicar un motivo.", "error")
            return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        minutos = None
        if tipo == "HORAS":
            minutos = _minutos_desde_hhmm(hhmm)
            if not minutos:
                flash("Para 'Horas', debes indicar un tiempo válido (HH:MM) mayor a 00:00.", "error")
                return redirect(url_for("inasistencias.nuevo", trabajador_id=trabajador_id))

        creadas, omitidas = 0, 0

        fecha_iter = fecha_desde
        for _ in range(dias):
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
                motivo=motivo,
                observacion=observacion,
                creado_por_user_id=getattr(current_user, "id", None),
            ))
            creadas += 1
            fecha_iter += timedelta(days=1)

        db.session.commit()

        if not (creadas > 0):
            flash("No se creó ningún registro (probablemente eran duplicados).", "warning")
        else:
            flash(f"Inasistencias registradas. Creadas: {creadas} · Omitidas: {omitidas}", "success")

        return redirect(url_for("inasistencias.listado", trabajador_id=trabajador_id))

    return render_template(
        "inasistencias/nuevo.html",
        trabajadores=trabajadores,
        hoy=date.today(),
        pre_trabajador_id=pre_trabajador_id,
        pre_trabajador_label=pre_trabajador_label,
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

        if not motivo:
            flash("Debes indicar un motivo.", "error")
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
        item.motivo = motivo
        item.observacion = observacion
        item.contrato_id = contrato_id

        db.session.commit()
        flash("Inasistencia actualizada.", "success")

        if next_url:
            return redirect(next_url)
        return redirect(url_for("inasistencias.listado", trabajador_id=item.trabajador_id))

    return render_template(
        "inasistencias/editar.html",
        item=item,
        trabajadores=trabajadores,
        hhmm=_fmt_hhmm(item.minutos_ausentes),
        next_url=next_url,
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
@role_required("ADMIN", "OPERADOR")
def revision():
    cc = (request.args.get("cc") or "").strip()
    mes = (request.args.get("mes") or "").strip()

    q = (
        Inasistencia.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == Trabajador.obra_id)
        .options(
            joinedload(Inasistencia.trabajador).joinedload(Trabajador.obra)
        )
    )

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

    if request.method == "POST":
        ids = request.form.getlist("inasistencia_id")
        if ids:
            Inasistencia.query.filter(Inasistencia.id.in_(ids)).update(
                {"procesada": True, "procesada_en": datetime.utcnow()},
                synchronize_session=False,
            )
            db.session.commit()
            flash(f"{len(ids)} inasistencias marcadas como procesadas.", "success")
        return redirect(url_for("inasistencias.revision", cc=cc, mes=mes))

    items = q.order_by(
        Trabajador.ap_paterno.asc(),
        Trabajador.ap_materno.asc(),
        Trabajador.nombres.asc(),
        Inasistencia.fecha.asc(),
        Inasistencia.id.asc(),
    ).all()

    centros_costo = _centros_costo()

    return render_template(
        "inasistencias/revision.html",
        items=items,
        centros_costo=centros_costo,
        cc=cc,
        mes=mes,
        fmt_hhmm=_fmt_hhmm,
    )
