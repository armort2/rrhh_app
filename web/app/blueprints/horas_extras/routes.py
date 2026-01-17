# web/app/blueprints/horas_extras/routes.py
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import HorasExtra, Trabajador, Contrato, Obra
from app.utils import parse_date, parse_int
from app.auth.decorators import role_required

from . import bp


# ---------------------------
# Helpers
# ---------------------------
def _parse_time_hhmm(value: str | None):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except Exception:
        return None


def _calc_minutes(inicio, termino) -> int:
    # Mismo día (si luego quieren cruzar medianoche, se ajusta)
    dt_i = datetime.combine(date.today(), inicio)
    dt_t = datetime.combine(date.today(), termino)
    delta = dt_t - dt_i
    return max(0, int(delta.total_seconds() // 60))


def _fmt_hhmm_from_minutes(minutos: int | None) -> str:
    if not minutos:
        return ""
    hh = minutos // 60
    mm = minutos % 60
    return f"{hh:02d}:{mm:02d}"


def _fmt_hhmm_time(t) -> str:
    if not t:
        return ""
    try:
        return t.strftime("%H:%M")
    except Exception:
        return ""


def _safe_next(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("/") and not url.startswith("//"):
        return url
    return None


def _current_full_path() -> str:
    full = request.full_path
    return full[:-1] if full.endswith("?") else full


def _contrato_vigente_para(trabajador_id: int, fecha_ref: date) -> Contrato | None:
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
    rows = (
        db.session.query(func.trim(Obra.centro_costo))
        .filter(Obra.centro_costo.isnot(None))
        .filter(func.trim(Obra.centro_costo) != "")
        .distinct()
        .order_by(func.trim(Obra.centro_costo).asc())
        .all()
    )
    return [r[0] for r in rows if r and r[0]]


def _usuario_puede_ver_obra(obra_id: int | None) -> bool:
    if not obra_id:
        return False
    # ADMIN ve todo; otros solo obras asignadas
    return bool(getattr(current_user, "can_access_obra", lambda _id: False)(obra_id))


# ---------------------------
# Listado
# ---------------------------
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR")
def listado():
    trabajador_id = parse_int(request.args.get("trabajador_id"))
    cc = (request.args.get("cc") or "").strip()
    mes = (request.args.get("mes") or "").strip()  # YYYY-MM
    estado = (request.args.get("estado") or "").strip().upper()

    q = (
        HorasExtra.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == HorasExtra.obra_id)
        .options(
            joinedload(HorasExtra.trabajador).joinedload(Trabajador.obra),
            joinedload(HorasExtra.obra),
        )
    )

    # Filtro seguridad: si no es ADMIN, limitar a obras asignadas
    if not current_user.has_role("ADMIN"):
        allowed_ids = [o.id for o in (current_user.obras or [])]
        if not allowed_ids:
            q = q.filter(False)  # no verá nada
        else:
            q = q.filter(HorasExtra.obra_id.in_(allowed_ids))

    if trabajador_id:
        q = q.filter(HorasExtra.trabajador_id == trabajador_id)

    if cc:
        q = q.filter(func.trim(Obra.centro_costo) == cc)

    if mes:
        try:
            y_str, m_str = mes.split("-")
            y = int(y_str)
            m = int(m_str)
            desde = date(y, m, 1)
            hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            q = q.filter(HorasExtra.fecha >= desde, HorasExtra.fecha < hasta)
        except Exception:
            flash("Mes inválido. Usa formato YYYY-MM.", "warning")

    if estado in ("PENDIENTE", "APROBADA", "RECHAZADA"):
        q = q.filter(HorasExtra.estado == estado)
    elif estado:
        flash("Estado inválido. Usa PENDIENTE / APROBADA / RECHAZADA.", "warning")

    items = q.order_by(HorasExtra.fecha.desc(), HorasExtra.id.desc()).limit(500).all()

    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    return render_template(
        "horas_extras/listado.html",
        items=items,
        trabajadores=trabajadores,
        centros_costo=centros_costo,
        trabajador_id=trabajador_id,
        cc=cc,
        mes=mes,
        estado=estado,
        fmt_minutes=_fmt_hhmm_from_minutes,
        fmt_time=_fmt_hhmm_time,
        next_url=_current_full_path(),
    )


# ---------------------------
# Nuevo
# ---------------------------
@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def nuevo():
    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    # Preselección opcional (?trabajador_id=123)
    pre_trabajador_id = parse_int(request.args.get("trabajador_id"))

    pre_trabajador_label = ""
    if pre_trabajador_id:
        t = Trabajador.query.get(pre_trabajador_id)
        if t:
            pre_trabajador_label = f"{t.id} - {t.ap_paterno} {t.ap_materno} {t.nombres} · RUT: {t.rut}"

    if request.method == "POST":
        trabajador_id = parse_int(request.form.get("trabajador_id"))
        fecha = parse_date(request.form.get("fecha"))
        hhmm_ini = (request.form.get("hora_inicio") or "").strip()
        hhmm_fin = (request.form.get("hora_termino") or "").strip()
        motivo = (request.form.get("motivo") or "").strip() or None

        # Obra: por defecto la obra actual del trabajador; opcionalmente podría venir forzada
        obra_id = parse_int(request.form.get("obra_id"))

        if not trabajador_id:
            flash("Debes seleccionar un trabajador.", "error")
            return redirect(url_for("horas_extras.nuevo"))

        t = Trabajador.query.get(trabajador_id)
        if not t:
            flash("Trabajador no existe.", "error")
            return redirect(url_for("horas_extras.nuevo"))

        if not fecha:
            flash("Debes indicar la fecha.", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        inicio = _parse_time_hhmm(hhmm_ini)
        termino = _parse_time_hhmm(hhmm_fin)
        if not inicio or not termino:
            flash("Debes indicar hora inicio y término válidas (HH:MM).", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        if termino <= inicio:
            flash("La hora término debe ser mayor a la hora inicio.", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        # Definir obra_id
        if not obra_id:
            obra_id = t.obra_id

        if not obra_id:
            flash("El trabajador no tiene obra asociada.", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        if not _usuario_puede_ver_obra(obra_id):
            flash("No tienes permisos para registrar horas extra en esa obra.", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        minutos = _calc_minutes(inicio, termino)
        if minutos <= 0:
            flash("El tramo horario no genera minutos válidos.", "error")
            return redirect(url_for("horas_extras.nuevo", trabajador_id=trabajador_id))

        # (Opcional) advertencia por exceso
        if minutos > 240:
            flash("Aviso: estás registrando más de 4 horas extra en un día. Revisa antes de guardar.", "warning")

        existe = (
            HorasExtra.query
            .filter_by(trabajador_id=trabajador_id, obra_id=obra_id, fecha=fecha, hora_inicio=inicio, hora_termino=termino)
            .first()
        )
        if existe:
            flash("Ya existe un registro idéntico para ese trabajador/fecha/tramo.", "warning")
            return redirect(url_for("horas_extras.listado", trabajador_id=trabajador_id))

        # Contrato vigente referencial (no lo guardamos hoy en tabla, pero validamos y advertimos)
        contrato = _contrato_vigente_para(trabajador_id, fecha)
        if not contrato:
            flash("Aviso: no se encontró contrato vigente para esa fecha (se guardará igual).", "warning")

        reg = HorasExtra(
            trabajador_id=trabajador_id,
            obra_id=obra_id,
            fecha=fecha,
            hora_inicio=inicio,
            hora_termino=termino,
            minutos_totales=minutos,
            motivo=motivo,
            estado="PENDIENTE",
        )

        db.session.add(reg)
        db.session.commit()

        flash("Horas extra registradas y enviadas a aprobación.", "success")
        return redirect(url_for("horas_extras.listado", trabajador_id=trabajador_id))

    # Para el selector de obra (si quieres permitir editar obra al registrar)
    obras = (
        Obra.query
        .order_by((Obra.estado == "ACTIVA").desc(), Obra.nombre.asc())
        .all()
    )

    # Filtro seguridad: no admin solo ve sus obras
    if not current_user.has_role("ADMIN"):
        allowed_ids = {o.id for o in (current_user.obras or [])}
        obras = [o for o in obras if o.id in allowed_ids]

    return render_template(
        "horas_extras/nuevo.html",
        trabajadores=trabajadores,
        obras=obras,
        hoy=date.today(),
        pre_trabajador_id=pre_trabajador_id,
        pre_trabajador_label=pre_trabajador_label,
        centros_costo=centros_costo,
    )


# ---------------------------
# Editar
# ---------------------------
@bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def editar(item_id: int):
    item = HorasExtra.query.options(
        joinedload(HorasExtra.trabajador).joinedload(Trabajador.obra),
        joinedload(HorasExtra.obra),
    ).get_or_404(item_id)

    if not _usuario_puede_ver_obra(item.obra_id):
        flash("No tienes permisos para acceder a este registro.", "error")
        return redirect(url_for("horas_extras.listado"))

    next_url = _safe_next(request.args.get("next")) or _safe_next(request.form.get("next"))

    # Regla: si está APROBADA, solo ADMIN puede editar (o derechamente nadie; aquí lo dejamos conservador)
    if item.estado == "APROBADA" and not current_user.has_role("ADMIN"):
        flash("No puedes editar un registro APROBADO.", "error")
        return redirect(next_url or url_for("horas_extras.listado"))

    if request.method == "POST":
        fecha = parse_date(request.form.get("fecha"))
        hhmm_ini = (request.form.get("hora_inicio") or "").strip()
        hhmm_fin = (request.form.get("hora_termino") or "").strip()
        motivo = (request.form.get("motivo") or "").strip() or None

        inicio = _parse_time_hhmm(hhmm_ini)
        termino = _parse_time_hhmm(hhmm_fin)

        if not fecha:
            flash("Debes indicar la fecha.", "error")
            return redirect(url_for("horas_extras.editar", item_id=item_id, next=next_url) if next_url else url_for("horas_extras.editar", item_id=item_id))

        if not inicio or not termino:
            flash("Debes indicar hora inicio y término válidas (HH:MM).", "error")
            return redirect(url_for("horas_extras.editar", item_id=item_id, next=next_url) if next_url else url_for("horas_extras.editar", item_id=item_id))

        if termino <= inicio:
            flash("La hora término debe ser mayor a la hora inicio.", "error")
            return redirect(url_for("horas_extras.editar", item_id=item_id, next=next_url) if next_url else url_for("horas_extras.editar", item_id=item_id))

        minutos = _calc_minutes(inicio, termino)
        if minutos <= 0:
            flash("El tramo horario no genera minutos válidos.", "error")
            return redirect(url_for("horas_extras.editar", item_id=item_id, next=next_url) if next_url else url_for("horas_extras.editar", item_id=item_id))

        item.fecha = fecha
        item.hora_inicio = inicio
        item.hora_termino = termino
        item.minutos_totales = minutos
        item.motivo = motivo

        # Si estaba RECHAZADA, vuelve a PENDIENTE (buena práctica)
        if item.estado == "RECHAZADA":
            item.estado = "PENDIENTE"
            item.autorizado_por = None
            item.observacion_revision = None

        db.session.commit()
        flash("Horas extra actualizadas.", "success")

        return redirect(next_url or url_for("horas_extras.listado"))

    return render_template(
        "horas_extras/editar.html",
        item=item,
        hhmm_ini=_fmt_hhmm_time(item.hora_inicio),
        hhmm_fin=_fmt_hhmm_time(item.hora_termino),
        next_url=next_url,
    )


# ---------------------------
# Eliminar
# ---------------------------
@bp.post("/<int:item_id>/eliminar")
@login_required
@role_required("ADMIN", "OPERADOR")
def eliminar(item_id: int):
    item = HorasExtra.query.get_or_404(item_id)

    if not _usuario_puede_ver_obra(item.obra_id):
        flash("No tienes permisos para eliminar este registro.", "error")
        return redirect(url_for("horas_extras.listado"))

    # Conservador: solo ADMIN elimina aprobadas
    if item.estado == "APROBADA" and not current_user.has_role("ADMIN"):
        flash("No puedes eliminar un registro APROBADO.", "error")
        return redirect(url_for("horas_extras.listado"))

    next_url = _safe_next(request.args.get("next")) or _safe_next(request.form.get("next"))

    db.session.delete(item)
    db.session.commit()

    flash("Registro eliminado.", "success")
    return redirect(next_url or url_for("horas_extras.listado"))


# ---------------------------
# Aprobar / Rechazar
# ---------------------------
@bp.post("/<int:item_id>/aprobar")
@login_required
@role_required("ADMIN", "REVISOR")
def aprobar(item_id: int):
    item = HorasExtra.query.get_or_404(item_id)

    if not _usuario_puede_ver_obra(item.obra_id):
        flash("No tienes permisos para aprobar en esta obra.", "error")
        return redirect(url_for("horas_extras.listado"))

    if item.estado == "APROBADA":
        flash("Este registro ya está APROBADO.", "warning")
        return redirect(url_for("horas_extras.listado"))

    item.estado = "APROBADA"
    item.autorizado_por = (getattr(current_user, "nombre", None) or getattr(current_user, "username", None) or "").strip() or None
    item.observacion_revision = (request.form.get("observacion_revision") or "").strip() or None

    db.session.commit()
    flash("Registro aprobado.", "success")
    return redirect(_safe_next(request.form.get("next")) or url_for("horas_extras.listado"))


@bp.post("/<int:item_id>/rechazar")
@login_required
@role_required("ADMIN", "REVISOR")
def rechazar(item_id: int):
    item = HorasExtra.query.get_or_404(item_id)

    if not _usuario_puede_ver_obra(item.obra_id):
        flash("No tienes permisos para rechazar en esta obra.", "error")
        return redirect(url_for("horas_extras.listado"))

    if item.estado == "RECHAZADA":
        flash("Este registro ya está RECHAZADO.", "warning")
        return redirect(url_for("horas_extras.listado"))

    obs = (request.form.get("observacion_revision") or "").strip()
    if not obs:
        flash("Para rechazar, debes indicar una observación.", "error")
        return redirect(url_for("horas_extras.listado"))

    item.estado = "RECHAZADA"
    item.autorizado_por = (getattr(current_user, "nombre", None) or getattr(current_user, "username", None) or "").strip() or None
    item.observacion_revision = obs

    db.session.commit()
    flash("Registro rechazado.", "success")
    return redirect(_safe_next(request.form.get("next")) or url_for("horas_extras.listado"))

# ---------------------------
# Revisión masiva
# ---------------------------
@bp.route("/revision", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "REVISOR")
def revision():
    cc = (request.values.get("cc") or "").strip()
    mes = (request.values.get("mes") or "").strip()  # YYYY-MM
    estado = (request.values.get("estado") or "PENDIENTE").strip().upper()

    centros_costo = _centros_costo()
    items = []

    # Seguridad: si no es ADMIN, limitar a obras asignadas
    allowed_ids = None
    if not current_user.has_role("ADMIN"):
        allowed_ids = [o.id for o in (current_user.obras or [])]
        if not allowed_ids:
            allowed_ids = []

    def _query_items():
        q = (
            HorasExtra.query
            .join(Trabajador)
            .outerjoin(Obra, Obra.id == HorasExtra.obra_id)
            .options(
                joinedload(HorasExtra.trabajador).joinedload(Trabajador.obra),
                joinedload(HorasExtra.obra),
            )
        )

        if allowed_ids is not None:
            if not allowed_ids:
                return q.filter(False)
            q = q.filter(HorasExtra.obra_id.in_(allowed_ids))

        if cc:
            q = q.filter(func.trim(Obra.centro_costo) == cc)

        if mes:
            try:
                y_str, m_str = mes.split("-")
                y = int(y_str)
                m = int(m_str)
                desde = date(y, m, 1)
                hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
                q = q.filter(HorasExtra.fecha >= desde, HorasExtra.fecha < hasta)
            except Exception:
                flash("Mes inválido. Usa formato YYYY-MM.", "warning")

        if estado in ("PENDIENTE", "APROBADA", "RECHAZADA"):
            q = q.filter(HorasExtra.estado == estado)
        elif estado:
            flash("Estado inválido. Usa PENDIENTE / APROBADA / RECHAZADA.", "warning")

        return q.order_by(HorasExtra.fecha.asc(), HorasExtra.id.asc()).limit(2000)

    if request.method == "POST":
        accion = (request.form.get("accion") or "").strip().upper()
        obs = (request.form.get("observacion_revision") or "").strip()
        ids = request.form.getlist("ids")

        if not ids:
            flash("Debes seleccionar al menos un registro.", "error")
            return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado=estado))

        if accion not in ("APROBAR", "RECHAZAR"):
            flash("Acción inválida.", "error")
            return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado=estado))

        if accion == "RECHAZAR" and not obs:
            flash("Para rechazar, debes indicar una observación.", "error")
            return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado=estado))

        # Cargar registros y aplicar seguridad por obra
        q = HorasExtra.query.filter(HorasExtra.id.in_([int(x) for x in ids if str(x).isdigit()]))

        if allowed_ids is not None:
            if not allowed_ids:
                flash("No tienes permisos para revisar registros.", "error")
                return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado=estado))
            q = q.filter(HorasExtra.obra_id.in_(allowed_ids))

        regs = q.all()
        if not regs:
            flash("No se encontraron registros válidos para aplicar la acción.", "error")
            return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado=estado))

        nombre_autor = (getattr(current_user, "nombre", None) or getattr(current_user, "username", None) or "").strip() or None

        changed = 0
        for r in regs:
            # Conservador: solo cambia si está pendiente
            if r.estado != "PENDIENTE":
                continue

            if accion == "APROBAR":
                r.estado = "APROBADA"
                r.autorizado_por = nombre_autor
                # observación opcional al aprobar
                r.observacion_revision = obs or None
                changed += 1
            else:
                r.estado = "RECHAZADA"
                r.autorizado_por = nombre_autor
                r.observacion_revision = obs
                changed += 1

        db.session.commit()
        flash(f"Acción aplicada a {changed} registro(s).", "success")
        return redirect(url_for("horas_extras.revision", cc=cc, mes=mes, estado="PENDIENTE"))

    # GET
    if cc and mes:
        items = _query_items().all()

    return render_template(
        "horas_extras/revision.html",
        items=items,
        centros_costo=centros_costo,
        cc=cc,
        mes=mes,
        estado=estado,
        fmt_minutes=_fmt_hhmm_from_minutes,
        fmt_time=_fmt_hhmm_time,
    )
