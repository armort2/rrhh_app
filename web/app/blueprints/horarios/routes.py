from __future__ import annotations

from datetime import time
from typing import List, Tuple

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...extensions import db
from ...models import Contrato, Horario, HorarioTramo
from ...utils import parse_int
from . import bp


# ---------------------------
# Helpers
# ---------------------------

DIA_LABELS = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}


def _require_admin() -> None:
    """
    Guardia de seguridad (literalmente) para este módulo.
    """
    if not (current_user.is_authenticated and current_user.has_role("ADMIN")):
        abort(403)


def parse_time_hhmm(val: str | None) -> time | None:
    if not val:
        return None
    val = val.strip()
    try:
        hh, mm = val.split(":")
        return time(int(hh), int(mm))
    except Exception:
        return None


def _leer_tramos_desde_form() -> List[Tuple[int, time, time, int]]:
    """
    Lee arreglos tipo:
      tramos_dia[], tramos_inicio[], tramos_termino[], tramos_orden[]
    y devuelve lista de tuplas validadas.
    """
    dias = request.form.getlist("tramos_dia")
    inis = request.form.getlist("tramos_inicio")
    ters = request.form.getlist("tramos_termino")
    ords = request.form.getlist("tramos_orden")

    tramos: List[Tuple[int, time, time, int]] = []

    total = max(len(dias), len(inis), len(ters), len(ords))
    for i in range(total):
        dia = parse_int(dias[i] if i < len(dias) else None)
        ini = parse_time_hhmm(inis[i] if i < len(inis) else None)
        ter = parse_time_hhmm(ters[i] if i < len(ters) else None)
        orden = parse_int(ords[i] if i < len(ords) else None) or 1

        # Si la fila está “vacía”, la ignoramos
        if dia is None and ini is None and ter is None:
            continue

        # Validaciones duras
        if dia is None or dia < 0 or dia > 6:
            raise ValueError(f"Día inválido en fila {i+1}.")
        if ini is None or ter is None:
            raise ValueError(f"Hora inicio/término inválida en fila {i+1}.")
        if ini >= ter:
            raise ValueError(f"Hora inicio debe ser menor a término (fila {i+1}).")

        tramos.append((dia, ini, ter, orden))

    # Orden estable por día + orden
    tramos.sort(key=lambda x: (x[0], x[3], x[1]))
    return tramos


# ---------------------------
# Listado
# ---------------------------

@bp.route("/", methods=["GET"])
@login_required
def horarios_listado():
    _require_admin()

    q = (request.args.get("q") or "").strip().lower()
    solo_activos = request.args.get("activos") == "1"

    query = Horario.query
    if q:
        query = query.filter(Horario.nombre.ilike(f"%{q}%"))
    if solo_activos:
        query = query.filter(Horario.activo.is_(True))

    horarios = query.order_by(Horario.activo.desc(), Horario.nombre.asc()).all()

    return render_template(
        "horarios_listado.html",
        horarios=horarios,
        q=q,
        solo_activos=solo_activos,
        DIA_LABELS=DIA_LABELS,
    )


# ---------------------------
# Crear
# ---------------------------

@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def horario_nuevo():
    _require_admin()

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        descripcion = (request.form.get("descripcion") or "").strip() or None
        activo = request.form.get("activo") == "1"

        if not nombre:
            flash("Debes indicar un nombre para el horario.", "error")
            return redirect(url_for("horarios.horario_nuevo"))

        # Unicidad de nombre
        existe = Horario.query.filter_by(nombre=nombre).first()
        if existe:
            flash("Ya existe un horario con ese nombre.", "error")
            return redirect(url_for("horarios.horario_nuevo"))

        try:
            tramos = _leer_tramos_desde_form()
            if not tramos:
                flash("Debes registrar al menos un tramo horario.", "error")
                return redirect(url_for("horarios.horario_nuevo"))
        except Exception as e:
            flash(str(e), "error")
            return redirect(url_for("horarios.horario_nuevo"))

        h = Horario(nombre=nombre, descripcion=descripcion, activo=activo)
        db.session.add(h)
        db.session.flush()  # para obtener h.id

        for (dia, ini, ter, orden) in tramos:
            db.session.add(
                HorarioTramo(
                    horario_id=h.id,
                    dia_semana=dia,
                    hora_inicio=ini,
                    hora_termino=ter,
                    orden=orden,
                )
            )

        db.session.commit()
        flash("Horario creado correctamente.", "success")
        return redirect(url_for("horarios.horarios_listado"))

    # GET: pre-cargamos una fila vacía para UX
    return render_template(
        "horario_form.html",
        modo="nuevo",
        horario=None,
        tramos=[],
        DIA_LABELS=DIA_LABELS,
    )


# ---------------------------
# Editar
# ---------------------------

@bp.route("/<int:horario_id>/editar", methods=["GET", "POST"])
@login_required
def horario_editar(horario_id: int):
    _require_admin()

    horario = Horario.query.get_or_404(horario_id)

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        descripcion = (request.form.get("descripcion") or "").strip() or None
        activo = request.form.get("activo") == "1"

        if not nombre:
            flash("Debes indicar un nombre para el horario.", "error")
            return redirect(url_for("horarios.horario_editar", horario_id=horario.id))

        # Unicidad (excluyendo el actual)
        existe = Horario.query.filter(Horario.nombre == nombre, Horario.id != horario.id).first()
        if existe:
            flash("Ya existe otro horario con ese nombre.", "error")
            return redirect(url_for("horarios.horario_editar", horario_id=horario.id))

        try:
            tramos = _leer_tramos_desde_form()
            if not tramos:
                flash("Debes registrar al menos un tramo horario.", "error")
                return redirect(url_for("horarios.horario_editar", horario_id=horario.id))
        except Exception as e:
            flash(str(e), "error")
            return redirect(url_for("horarios.horario_editar", horario_id=horario.id))

        horario.nombre = nombre
        horario.descripcion = descripcion
        horario.activo = activo

        # Reemplazo simple y seguro: borramos tramos y recreamos.
        HorarioTramo.query.filter_by(horario_id=horario.id).delete()
        for (dia, ini, ter, orden) in tramos:
            db.session.add(
                HorarioTramo(
                    horario_id=horario.id,
                    dia_semana=dia,
                    hora_inicio=ini,
                    hora_termino=ter,
                    orden=orden,
                )
            )

        db.session.commit()
        flash("Horario actualizado correctamente.", "success")
        return redirect(url_for("horarios.horarios_listado"))

    tramos = (
        HorarioTramo.query
        .filter_by(horario_id=horario.id)
        .order_by(HorarioTramo.dia_semana.asc(), HorarioTramo.orden.asc())
        .all()
    )
    return render_template(
        "horario_form.html",
        modo="editar",
        horario=horario,
        tramos=tramos,
        DIA_LABELS=DIA_LABELS,
    )


# ---------------------------
# Activar / Desactivar
# ---------------------------

@bp.post("/<int:horario_id>/toggle")
@login_required
def horario_toggle(horario_id: int):
    _require_admin()

    horario = Horario.query.get_or_404(horario_id)
    horario.activo = not bool(horario.activo)
    db.session.commit()
    flash("Estado del horario actualizado.", "success")
    return redirect(url_for("horarios.horarios_listado"))


# ---------------------------
# Eliminar (solo si no está usado)
# ---------------------------

@bp.post("/<int:horario_id>/eliminar")
@login_required
def horario_eliminar(horario_id: int):
    _require_admin()

    horario = Horario.query.get_or_404(horario_id)

    usado = Contrato.query.filter_by(horario_id=horario.id).first()
    if usado:
        flash(
            "No se puede eliminar: este horario está asociado a uno o más contratos. "
            "Recomendado: desactívalo.",
            "error",
        )
        return redirect(url_for("horarios.horarios_listado"))

    db.session.delete(horario)
    db.session.commit()
    flash("Horario eliminado correctamente.", "success")
    return redirect(url_for("horarios.horarios_listado"))
