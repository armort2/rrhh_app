# web/app/blueprints/horas_extras/routes.py
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from zoneinfo import ZoneInfo
from itertools import groupby

from app.extensions import db
from app.models import HorasExtra, Trabajador, Contrato, Obra, Empleador, PactoHorasExtra
from app.utils import parse_date, parse_int
from app.auth.decorators import role_required
from app.services.pactos_hr_extras_docs import generar_docx_y_pdf_pacto_horas_extra

from . import bp
import os
import calendar

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

def _parse_date_yyyy_mm_dd(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _pacto_rango_valido(fecha_inicio: date | None, fecha_termino: date | None) -> tuple[bool, str | None]:
    if not fecha_inicio or not fecha_termino:
        return False, "Debes indicar fecha de inicio y fecha de término."

    if fecha_termino < fecha_inicio:
        return False, "La fecha de término no puede ser menor que la fecha de inicio."

    dias = (fecha_termino - fecha_inicio).days
    if dias > 92:
        return False, "El pacto no puede tener una vigencia superior a 3 meses."

    return True, None


def _allowed_obra_ids_for_current_user() -> list[int]:
    if current_user.has_role("ADMIN"):
        return []
    return [o.id for o in (current_user.obras or [])]


def _query_pactos_base():
    q = (
        PactoHorasExtra.query
        .join(Trabajador, Trabajador.id == PactoHorasExtra.trabajador_id)
        .outerjoin(Obra, Obra.id == PactoHorasExtra.obra_id)
        .outerjoin(Empleador, Empleador.id == PactoHorasExtra.empleador_id)
        .options(
            joinedload(PactoHorasExtra.trabajador),
            joinedload(PactoHorasExtra.contrato),
            joinedload(PactoHorasExtra.obra),
            joinedload(PactoHorasExtra.empleador),
        )
    )

    if not current_user.has_role("ADMIN"):
        allowed_ids = _allowed_obra_ids_for_current_user()
        if not allowed_ids:
            q = q.filter(False)
        else:
            q = q.filter(PactoHorasExtra.obra_id.in_(allowed_ids))

    return q    


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


def _ultimo_dia_del_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def _sumar_meses(fecha: date, meses: int) -> date:
    """
    Suma meses respetando el último día válido del mes destino.
    """
    year = fecha.year + ((fecha.month - 1 + meses) // 12)
    month = ((fecha.month - 1 + meses) % 12) + 1
    day = min(fecha.day, _ultimo_dia_del_mes(year, month))
    return date(year, month, day)


def _fecha_termino_max_pacto(fecha_inicio: date | None) -> date | None:
    """
    Regla del pacto:
    - Si inicia el día 1 del mes -> termina el último día del 3er mes posterior "contractual".
      Ej: 01-04-2026 -> 30-06-2026
    - En cualquier otro caso -> mismo día, 3 meses después.
      Ej: 14-04-2026 -> 14-07-2026
    """
    if not fecha_inicio:
        return None

    if fecha_inicio.day == 1:
        # Tomamos el mes de inicio + 2 y devolvemos su último día
        target = _sumar_meses(fecha_inicio, 2)
        ultimo = _ultimo_dia_del_mes(target.year, target.month)
        return date(target.year, target.month, ultimo)

    return _sumar_meses(fecha_inicio, 3)


def _pacto_rango_valido(fecha_inicio: date | None, fecha_termino: date | None) -> tuple[bool, str | None]:
    """
    Valida el rango del pacto según regla de máximo 3 meses.
    """
    if not fecha_inicio:
        return False, "Debes indicar la fecha de inicio del pacto."

    if not fecha_termino:
        return False, "Debes indicar la fecha de término del pacto."

    if fecha_termino < fecha_inicio:
        return False, "La fecha de término no puede ser anterior a la fecha de inicio."

    fecha_max = _fecha_termino_max_pacto(fecha_inicio)
    if fecha_max is None:
        return False, "No fue posible calcular la vigencia máxima del pacto."

    if fecha_termino > fecha_max:
        return (
            False,
            f"El pacto excede la vigencia máxima permitida. Para una fecha de inicio {fecha_inicio.isoformat()}, "
            f"la fecha máxima de término es {fecha_max.isoformat()}."
        )

    return True, None

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

    if not current_user.has_role("ADMIN"):
        allowed_ids = [o.id for o in (current_user.obras or [])]
        if not allowed_ids:
            q = q.filter(False)
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

    # ✅ Agrupar por día (igual que inasistencias)
    dias = [(f, list(g)) for f, g in groupby(items, key=lambda x: x.fecha)]

    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    return render_template(
        "horas_extras/listado.html",
        items=items,
        dias=dias,
        trabajadores=trabajadores,
        centros_costo=centros_costo,
        trabajador_id=trabajador_id,
        cc=cc,
        mes=mes,
        mes_default=mes_default,
        estado=estado,
        hoy=hoy,
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


def _format_rut(body: str | int | None, dv: str | None) -> str:
    if body is None:
        return ""
    body_str = str(body).strip().replace(".", "").replace("-", "").replace(" ", "")
    dv_str = (dv or "").strip().upper()
    if not body_str:
        return ""
    body_digits = "".join(ch for ch in body_str if ch.isdigit())
    if not body_digits:
        return ""
    body_fmt = f"{int(body_digits):,}".replace(",", ".")
    return f"{body_fmt}-{dv_str}" if dv_str else body_fmt


@bp.route("/revision-remuneraciones", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def revision_remu():
    cc = (request.values.get("cc") or "").strip()

    tz_cl = ZoneInfo("America/Santiago")
    hoy = datetime.now(tz_cl).date()
    mes_default = hoy.strftime("%Y-%m")
    mes = (request.values.get("mes") or "").strip() or mes_default

    estado = (request.values.get("estado") or "").strip() or "APROBADA"
    estado = estado.upper()
    ingreso = (request.values.get("ingreso") or "").strip() or "pendientes"
    if ingreso not in ("pendientes", "procesadas", "todas"):
        ingreso = "pendientes"

    q = (
        HorasExtra.query
        .join(Trabajador)
        .outerjoin(Obra, Obra.id == HorasExtra.obra_id)
        .options(
            joinedload(HorasExtra.trabajador).joinedload(Trabajador.obra),
            joinedload(HorasExtra.obra),
        )
    )

    # Seguridad por obra (si quisieras permitirlo también acá)
    if not current_user.has_role("ADMIN"):
        allowed_ids = [o.id for o in (current_user.obras or [])]
        if not allowed_ids:
            q = q.filter(False)
        else:
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

    if estado != "TODAS":
        if estado in ("PENDIENTE", "APROBADA", "RECHAZADA"):
            q = q.filter(HorasExtra.estado == estado)
        else:
            flash("Estado inválido.", "warning")
            estado = "APROBADA"
            q = q.filter(HorasExtra.estado == "APROBADA")

    # Filtro por “ingreso en remuneraciones”
    if ingreso == "pendientes":
        q = q.filter(HorasExtra.remu_procesada.is_(False))
    elif ingreso == "procesadas":
        q = q.filter(HorasExtra.remu_procesada.is_(True))

    # POST: marcar ingresadas (SOLO APROBADAS)
    if request.method == "POST":
        trabajador_post = parse_int(request.form.get("trabajador_id"))

        nombre_autor = (getattr(current_user, "nombre", None) or getattr(current_user, "username", None) or "").strip() or None
        now_utc = datetime.utcnow()

        if trabajador_post:
            q_upd = HorasExtra.query.filter(
                HorasExtra.trabajador_id == trabajador_post,
                HorasExtra.remu_procesada.is_(False),
                HorasExtra.estado == "APROBADA",  # ✅ Control interno: solo aprobadas
            )

            # Reaplicar filtros de contexto
            if cc:
                q_upd = (
                    q_upd.join(Obra, Obra.id == HorasExtra.obra_id)
                    .filter(func.trim(Obra.centro_costo) == cc)
                )

            if mes:
                try:
                    y_str, m_str = mes.split("-")
                    y = int(y_str)
                    m = int(m_str)
                    desde = date(y, m, 1)
                    hasta = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
                    q_upd = q_upd.filter(HorasExtra.fecha >= desde, HorasExtra.fecha < hasta)
                except Exception:
                    pass

            # Importante:
            # NO aplicamos el filtro "estado" del UI al update, porque podría permitir marcar PENDIENTES.
            # El control interno manda: APROBADA solamente.

            n = q_upd.update(
                {"remu_procesada": True, "remu_procesada_en": now_utc, "remu_procesada_por": nombre_autor},
                synchronize_session=False,
            )
            db.session.commit()

            flash(
                f"{n} registro(s) APROBADO(s) marcados como ingresados en remuneraciones para este trabajador.",
                "success",
            )
            return redirect(url_for(
                "horas_extras.revision_remu",
                cc=cc,
                mes=mes,
                estado=estado if estado != "TODAS" else "todas",
                ingreso=ingreso,
            ))

        ids = request.form.getlist("he_id")
        if ids:
            n = (
                HorasExtra.query
                .filter(HorasExtra.id.in_(ids))
                .filter(HorasExtra.remu_procesada.is_(False))
                .filter(HorasExtra.estado == "APROBADA")  # ✅ Control interno: solo aprobadas
                .update(
                    {"remu_procesada": True, "remu_procesada_en": now_utc, "remu_procesada_por": nombre_autor},
                    synchronize_session=False,
                )
            )
            db.session.commit()

            flash(f"{n} registro(s) APROBADO(s) marcados como ingresados en remuneraciones.", "success")

        return redirect(url_for(
            "horas_extras.revision_remu",
            cc=cc,
            mes=mes,
            estado=estado if estado != "TODAS" else "todas",
            ingreso=ingreso,
        ))

    items = q.order_by(
        Trabajador.ap_paterno.asc(),
        Trabajador.ap_materno.asc(),
        Trabajador.nombres.asc(),
        HorasExtra.fecha.asc(),
        HorasExtra.hora_inicio.asc(),
        HorasExtra.id.asc(),
    ).all()

    rut_fmt_map: dict[int, str] = {}
    for it in items:
        t = it.trabajador
        if not t or not t.id:
            continue
        rut_fmt_map[t.id] = _format_rut(getattr(t, "rut", None), getattr(t, "dv", None))

    centros_costo = _centros_costo()

    return render_template(
        "horas_extras/revision_remu.html",
        items=items,
        centros_costo=centros_costo,
        cc=cc,
        mes=mes,
        mes_default=mes_default,
        estado=("todas" if estado == "TODAS" else estado),
        ingreso=ingreso,
        fmt_minutes=_fmt_hhmm_from_minutes,
        fmt_time=_fmt_hhmm_time,
        rut_fmt_map=rut_fmt_map,
    )

# ===========================
# PACTOS DE HORAS EXTRA
# ===========================

@bp.get("/pactos")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def pactos_listado():
    trabajador_id = parse_int(request.args.get("trabajador_id"))
    cc = (request.args.get("cc") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    vigencia = (request.args.get("vigencia") or "").strip().upper()

    q = _query_pactos_base()

    if trabajador_id:
        q = q.filter(PactoHorasExtra.trabajador_id == trabajador_id)

    if cc:
        q = q.filter(func.trim(Obra.centro_costo) == cc)

    if estado in ("BORRADOR", "EMITIDO", "ANULADO"):
        q = q.filter(PactoHorasExtra.estado == estado)
    elif estado:
        flash("Estado inválido. Usa BORRADOR / EMITIDO / ANULADO.", "warning")

    items = q.order_by(
        PactoHorasExtra.fecha_inicio.desc(),
        PactoHorasExtra.id.desc(),
    ).limit(300).all()

    hoy = date.today()

    if vigencia == "VIGENTE":
        items = [x for x in items if x.vigente]
    elif vigencia == "VENCIDO":
        items = [x for x in items if x.vencido]
    elif vigencia == "POR_VENCER":
        items = [
            x for x in items
            if x.estado != "ANULADO"
            and x.dias_para_expirar is not None
            and 0 <= x.dias_para_expirar <= 7
        ]

    trabajadores = _trabajadores_para_selector()
    centros_costo = _centros_costo()

    return render_template(
        "horas_extras/pactos_listado.html",
        items=items,
        trabajadores=trabajadores,
        centros_costo=centros_costo,
        trabajador_id=trabajador_id,
        cc=cc,
        estado=estado,
        vigencia=vigencia,
        hoy=hoy,
    )


@bp.route("/pactos/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def pacto_nuevo():
    hoy = date.today()

    pre_trabajador_id = parse_int(request.args.get("trabajador_id"))
    pre_trabajador_label = ""

    if pre_trabajador_id:
        t = Trabajador.query.get(pre_trabajador_id)
        if t:
            pre_trabajador_label = " ".join([
                x for x in [
                    (t.ap_paterno or "").strip(),
                    (t.ap_materno or "").strip(),
                    (t.nombres or "").strip(),
                ] if x
            ]).strip()
            if getattr(t, "rut_completo", None):
                pre_trabajador_label = f"{pre_trabajador_label} · {t.rut_completo}"

    if request.method == "POST":
        trabajador_id = parse_int(request.form.get("trabajador_id"))
        contrato_id = parse_int(request.form.get("contrato_id"))

        fecha_inicio = parse_date(request.form.get("fecha_inicio"))
        fecha_termino = parse_date(request.form.get("fecha_termino"))
        fecha_emision = parse_date(request.form.get("fecha_emision")) or hoy
        observaciones = (request.form.get("observaciones") or "").strip() or None

        # ---------------------------
        # Validaciones base
        # ---------------------------
        if not trabajador_id:
            flash("Debes seleccionar un trabajador.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo"))

        trabajador = Trabajador.query.get(trabajador_id)
        if not trabajador:
            flash("El trabajador seleccionado no existe.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo"))

        if not contrato_id:
            flash("Debes seleccionar el contrato que se utilizará para emitir el pacto.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo", trabajador_id=trabajador_id))

        contrato = (
            Contrato.query
            .filter(
                Contrato.id == contrato_id,
                Contrato.trabajador_id == trabajador_id,
            )
            .first()
        )

        ok, err = _pacto_rango_valido(fecha_inicio, fecha_termino)

        if not contrato:
            flash("El contrato seleccionado no es válido para el trabajador indicado.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo", trabajador_id=trabajador_id))

        if not ok:
            flash(err, "error")
            return redirect(url_for("horas_extras.pacto_nuevo", trabajador_id=trabajador_id))

        # ---------------------------
        # Validación por obra / permisos
        # ---------------------------
        obra_id = contrato.obra_id
        empleador_id = contrato.empleador_id

        if not obra_id:
            flash("El contrato seleccionado no tiene obra asociada. No se puede emitir el pacto.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo", trabajador_id=trabajador_id))

        if not _usuario_puede_ver_obra(obra_id):
            flash("No tienes permisos para emitir pactos sobre la obra asociada a este contrato.", "error")
            return redirect(url_for("horas_extras.pacto_nuevo", trabajador_id=trabajador_id))

        # ---------------------------
        # Validación de duplicidad conservadora
        # ---------------------------
        existe = (
            PactoHorasExtra.query
            .filter(
                PactoHorasExtra.trabajador_id == trabajador_id,
                PactoHorasExtra.contrato_id == contrato_id,
                PactoHorasExtra.fecha_inicio == fecha_inicio,
                PactoHorasExtra.fecha_termino == fecha_termino,
                PactoHorasExtra.estado != "ANULADO",
            )
            .first()
        )

        if existe:
            flash("Ya existe un pacto activo o emitido con ese mismo trabajador, contrato y rango de fechas.", "warning")
            return redirect(url_for("horas_extras.pacto_detalle", pacto_id=existe.id))

        # ---------------------------
        # Crear pacto
        # ---------------------------
        pacto = PactoHorasExtra(
            trabajador_id=trabajador_id,
            contrato_id=contrato.id,
            empleador_id=empleador_id,
            obra_id=obra_id,
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,
            fecha_emision=fecha_emision,
            observaciones=observaciones,
            formato="AMBOS",
            estado="BORRADOR",
            meta={
                "creado_desde": "pacto_nuevo",
                "trabajador_nombre": " ".join([
                    x for x in [
                        (trabajador.ap_paterno or "").strip(),
                        (trabajador.ap_materno or "").strip(),
                        (trabajador.nombres or "").strip(),
                    ] if x
                ]).strip(),
                "contrato_estado": contrato.estado_contrato,
                "contrato_tipo": contrato.tipo_contrato,
            },
        )

        db.session.add(pacto)
        db.session.commit()

        flash("Pacto de horas extra creado en borrador.", "success")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    # ---------------------------
    # GET
    # ---------------------------
    return render_template(
        "horas_extras/pacto_form.html",
        modo="nuevo",
        pacto=None,
        hoy=hoy,
        pre_trabajador_id=pre_trabajador_id,
        pre_trabajador_label=pre_trabajador_label,
    )


@bp.get("/pactos/<int:pacto_id>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def pacto_detalle(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        flash("No tienes permisos para acceder a este pacto.", "error")
        return redirect(url_for("horas_extras.pactos_listado"))

    return render_template(
        "horas_extras/pacto_detalle.html",
        pacto=pacto,
        hoy=date.today(),
    )


@bp.route("/pactos/<int:pacto_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def pacto_editar(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        flash("No tienes permisos para editar este pacto.", "error")
        return redirect(url_for("horas_extras.pactos_listado"))

    if pacto.estado == "ANULADO":
        flash("No puedes editar un pacto ANULADO.", "warning")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    if request.method == "POST":
        fecha_inicio = _parse_date_yyyy_mm_dd(request.form.get("fecha_inicio"))
        fecha_termino = _parse_date_yyyy_mm_dd(request.form.get("fecha_termino"))
        fecha_emision = _parse_date_yyyy_mm_dd(request.form.get("fecha_emision")) or pacto.fecha_emision
        observaciones = (request.form.get("observaciones") or "").strip() or None

        ok, err = _pacto_rango_valido(fecha_inicio, fecha_termino)
        if not ok:
            flash(err, "error")
            return redirect(url_for("horas_extras.pacto_editar", pacto_id=pacto.id))

        # El pacto sigue amarrado al contrato original
        contrato = (
            Contrato.query
            .filter(
                Contrato.id == pacto.contrato_id,
                Contrato.trabajador_id == pacto.trabajador_id,
            )
            .first()
        )

        if not contrato:
            flash("El contrato asociado a este pacto ya no existe o no es válido.", "error")
            return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

        if contrato.obra_id and not _usuario_puede_ver_obra(contrato.obra_id):
            flash("No tienes permisos sobre la obra asociada al contrato de este pacto.", "error")
            return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

        # Sincronizamos contexto contractual
        pacto.contrato_id = contrato.id
        pacto.empleador_id = contrato.empleador_id
        pacto.obra_id = contrato.obra_id
        pacto.fecha_inicio = fecha_inicio
        pacto.fecha_termino = fecha_termino
        pacto.fecha_emision = fecha_emision
        pacto.observaciones = observaciones

        # 👇 CAPA PREMIUM:
        # si ya estaba emitido, vuelve a borrador y obliga reemisión documental
        if pacto.estado == "EMITIDO":
            pacto.estado = "BORRADOR"
            pacto.docx_nombre = None
            pacto.docx_ruta = None
            pacto.pdf_nombre = None
            pacto.pdf_ruta = None

        meta = dict(pacto.meta or {})
        meta["editado_en"] = datetime.now().isoformat()
        meta["editado_desde"] = "pacto_editar"
        pacto.meta = meta

        db.session.commit()

        if pacto.estado == "BORRADOR":
            flash("Pacto actualizado. Como fue modificado, quedó en BORRADOR y debe emitirse nuevamente.", "success")
        else:
            flash("Pacto actualizado correctamente.", "success")

        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    return render_template(
        "horas_extras/pacto_form.html",
        modo="editar",
        pacto=pacto,
        trabajadores=[],
        centros_costo=[],
        hoy=date.today(),
        pre_trabajador_id=None,
        pre_trabajador_label="",
    )


@bp.post("/pactos/<int:pacto_id>/emitir")
@login_required
@role_required("ADMIN", "OPERADOR")
def pacto_emitir(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        flash("No tienes permisos para emitir este pacto.", "error")
        return redirect(url_for("horas_extras.pactos_listado"))

    if pacto.estado == "ANULADO":
        flash("No puedes emitir un pacto ANULADO.", "warning")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    ok, err = _pacto_rango_valido(pacto.fecha_inicio, pacto.fecha_termino)
    if not ok:
        flash(err, "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    contrato = (
        Contrato.query
        .filter(
            Contrato.id == pacto.contrato_id,
            Contrato.trabajador_id == pacto.trabajador_id,
        )
        .first()
    )

    if not contrato:
        flash("El contrato asociado al pacto no existe o no es válido.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    if not contrato.empleador_id:
        flash("El contrato seleccionado no tiene empleador asociado. No se puede emitir el pacto.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    if not contrato.obra_id:
        flash("El contrato seleccionado no tiene obra asociada. No se puede emitir el pacto.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    if not _usuario_puede_ver_obra(contrato.obra_id):
        flash("No tienes permisos sobre la obra asociada al contrato de este pacto.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    # Sincronizamos contexto antes de emitir
    pacto.empleador_id = contrato.empleador_id
    pacto.obra_id = contrato.obra_id

    try:
        (
            docx_tmp_path, docx_nombre,
            pdf_tmp_path, pdf_nombre,
            docx_guardado_path, pdf_guardado_path,
        ) = generar_docx_y_pdf_pacto_horas_extra(pacto)

        pacto.docx_nombre = docx_nombre
        pacto.docx_ruta = docx_guardado_path or docx_tmp_path
        pacto.pdf_nombre = pdf_nombre
        pacto.pdf_ruta = pdf_guardado_path or pdf_tmp_path
        pacto.estado = "EMITIDO"

        meta = dict(pacto.meta or {})
        meta["emitido_en"] = datetime.now().isoformat()
        meta["emitido_desde"] = "pacto_emitir"
        pacto.meta = meta

        db.session.commit()
        flash("Pacto emitido correctamente (DOCX + PDF).", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"No fue posible emitir el pacto: {e}", "error")

    return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))


@bp.get("/pactos/<int:pacto_id>/descargar-docx")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def pacto_descargar_docx(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        abort(403)

    if not pacto.docx_ruta:
        flash("Este pacto aún no tiene DOCX generado.", "warning")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    path = pacto.docx_ruta
    if not os.path.exists(path):
        flash("No se encontró el archivo DOCX generado para este pacto.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    return send_file(path, as_attachment=True, download_name=pacto.docx_nombre or None)


@bp.get("/pactos/<int:pacto_id>/descargar-pdf")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def pacto_descargar_pdf(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        abort(403)

    if not pacto.pdf_ruta:
        flash("Este pacto aún no tiene PDF generado.", "warning")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    path = pacto.pdf_ruta
    if not os.path.exists(path):
        flash("No se encontró el archivo PDF generado para este pacto.", "error")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    return send_file(path, as_attachment=True, download_name=pacto.pdf_nombre or None)


@bp.post("/pactos/<int:pacto_id>/anular")
@login_required
@role_required("ADMIN", "OPERADOR")
def pacto_anular(pacto_id: int):
    pacto = _query_pactos_base().filter(PactoHorasExtra.id == pacto_id).first_or_404()

    if not _usuario_puede_ver_obra(pacto.obra_id):
        flash("No tienes permisos para anular este pacto.", "error")
        return redirect(url_for("horas_extras.pactos_listado"))

    if pacto.estado == "ANULADO":
        flash("Este pacto ya se encuentra anulado.", "warning")
        return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

    pacto.estado = "ANULADO"

    meta = dict(pacto.meta or {})
    meta["anulado_en"] = datetime.now().isoformat()
    meta["anulado_desde"] = "pacto_anular"
    pacto.meta = meta

    db.session.commit()

    flash("Pacto anulado.", "success")
    return redirect(url_for("horas_extras.pacto_detalle", pacto_id=pacto.id))

@bp.get("/api/trabajadores-buscar")
@login_required
@role_required("ADMIN", "OPERADOR")
def api_trabajadores_buscar():
    """
    Autocomplete de trabajadores para pactos / horas extra.
    Busca por nombres, apellidos y RUT, admitiendo múltiples términos
    en cualquier orden.
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return {"results": []}

    tokens = [tok.strip() for tok in q.split() if tok.strip()]
    if not tokens:
        return {"results": []}

    query = (
        Trabajador.query
        .outerjoin(Obra, Obra.id == Trabajador.obra_id)
    )

    # Seguridad por obra para usuarios no ADMIN
    if not current_user.has_role("ADMIN"):
        allowed_ids = [o.id for o in (current_user.obras or [])]
        if not allowed_ids:
            return {"results": []}
        query = query.filter(Trabajador.obra_id.in_(allowed_ids))

    # Cada token debe encontrarse en algún campo
    for tok in tokens:
        like = f"%{tok}%"
        query = query.filter(
            or_(
                Trabajador.rut.ilike(like),
                Trabajador.nombres.ilike(like),
                Trabajador.ap_paterno.ilike(like),
                Trabajador.ap_materno.ilike(like),
            )
        )

    rows = (
        query
        .order_by(
            Trabajador.ap_paterno.asc(),
            Trabajador.ap_materno.asc(),
            Trabajador.nombres.asc(),
        )
        .limit(20)
        .all()
    )

    results = []
    for t in rows:
        nombre = " ".join(
            x for x in [t.ap_paterno, t.ap_materno, t.nombres] if x
        ).strip()

        obra_nombre = ""
        if getattr(t, "obra", None):
            obra_nombre = (getattr(t.obra, "nombre", "") or "").strip()

        # Contrato vigente referencial a hoy
        contrato = _contrato_vigente_para(t.id, date.today())

        empleador_nombre = ""
        if contrato and getattr(contrato, "empleador", None):
            empleador_nombre = (getattr(contrato.empleador, "razon_social", "") or "").strip()
        elif getattr(t, "obra", None) and getattr(t.obra, "empleador", None):
            empleador_nombre = (getattr(t.obra.empleador, "razon_social", "") or "").strip()

        results.append({
            "id": t.id,
            "nombre": nombre,
            "rut": getattr(t, "rut_completo", "") or "",
            "obra": obra_nombre,
            "obra_id": getattr(t, "obra_id", None),
            "contrato_id": getattr(contrato, "id", None) if contrato else None,
            "empleador": empleador_nombre,
        })

    return {"results": results}

@bp.get("/api/trabajador-contratos")
@login_required
@role_required("ADMIN", "OPERADOR")
def api_trabajador_contratos():
    trabajador_id = parse_int(request.args.get("trabajador_id"))
    if not trabajador_id:
        return {"results": []}

    t = Trabajador.query.get(trabajador_id)
    if not t:
        return {"results": []}

    # Seguridad por obra
    if not current_user.has_role("ADMIN") and not _usuario_puede_ver_obra(getattr(t, "obra_id", None)):
        return {"results": []}

    contratos = (
        Contrato.query
        .filter(Contrato.trabajador_id == trabajador_id)
        .outerjoin(Empleador, Empleador.id == Contrato.empleador_id)
        .outerjoin(Obra, Obra.id == Contrato.obra_id)
        .order_by(
            (Contrato.estado_contrato == "VIGENTE").desc(),
            Contrato.fecha_inicio.desc(),
            Contrato.id.desc(),
        )
        .all()
    )

    results = []
    for c in contratos:
        empleador_nombre = (c.empleador.razon_social if c.empleador else "").strip() if c.empleador else ""
        obra_nombre = (c.obra.nombre if c.obra else "").strip() if c.obra else ""
        tipo_contrato = (c.tipo_contrato or "").strip()
        estado_contrato = (c.estado_contrato or "").strip()

        fecha_inicio = c.fecha_inicio.isoformat() if c.fecha_inicio else ""
        fecha_termino = c.fecha_termino.isoformat() if c.fecha_termino else ""

        etiqueta = (
            f"#{c.id} · {tipo_contrato or 'SIN TIPO'} · "
            f"{empleador_nombre or 'Sin empleador'} · "
            f"Obra: {obra_nombre or 'Sin obra'}"
        )

        results.append({
            "id": c.id,
            "label": etiqueta,
            "tipo_contrato": tipo_contrato,
            "estado_contrato": estado_contrato,
            "fecha_inicio": fecha_inicio,
            "fecha_termino": fecha_termino,
            "empleador_id": c.empleador_id,
            "empleador": empleador_nombre,
            "obra_id": c.obra_id,
            "obra": obra_nombre,
        })

    return {"results": results}