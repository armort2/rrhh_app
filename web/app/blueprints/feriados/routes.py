# web/app/blueprints/feriados/routes.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import extract, func

from ...extensions import db
from ...auth.decorators import role_required
from ...models import Feriado

from . import bp


# --------------------------
# Helpers
# --------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _year_or_default(value: str | None) -> int:
    try:
        y = int((value or "").strip())
        if 2000 <= y <= 2100:
            return y
    except Exception:
        pass
    return date.today().year


def _tipo_norm(value: str | None) -> str:
    v = (value or "").strip().upper()
    if v not in {"LEGAL", "REGIONAL", "EMPRESA"}:
        return "LEGAL"
    return v


# --------------------------
# Views
# --------------------------

@bp.get("/")
@login_required
@role_required("ADMIN")
def listado():
    """
    Listado de feriados por año.
    Solo ADMIN.
    """
    year = _year_or_default(request.args.get("year"))

    feriados = (
        Feriado.query
        .filter(extract("year", Feriado.fecha) == year)
        .order_by(Feriado.fecha.asc())
        .all()
    )

    # Para selector rápido
    # (Años disponibles + año actual +/- 1)
    years_db = (
        db.session.query(func.distinct(extract("year", Feriado.fecha)))
        .order_by(extract("year", Feriado.fecha).desc())
        .all()
    )
    years_db = [int(x[0]) for x in years_db if x and x[0] is not None]

    years = sorted(set(years_db + [date.today().year - 1, date.today().year, date.today().year + 1]), reverse=True)

    return render_template(
        "feriados/listado.html",
        feriados=feriados,
        year=year,
        years=years,
    )


@bp.get("/nuevo")
@login_required
@role_required("ADMIN")
def nuevo():
    return render_template(
        "feriados/form.html",
        modo="nuevo",
        f=None,
        year=_year_or_default(request.args.get("year")),
    )


@bp.post("/nuevo")
@login_required
@role_required("ADMIN")
def nuevo_post():
    fecha = _parse_date(request.form.get("fecha"))
    nombre = (request.form.get("nombre") or "").strip()
    tipo = _tipo_norm(request.form.get("tipo"))
    region = (request.form.get("region") or "").strip() or None
    activo = (request.form.get("activo") or "").strip().lower() in {"1", "true", "on", "si", "sí"}

    if not fecha:
        flash("Debes indicar la fecha del feriado.", "danger")
        return redirect(url_for("feriados.nuevo"))

    if not nombre:
        flash("Debes indicar el nombre/descripcion del feriado.", "danger")
        return redirect(url_for("feriados.nuevo"))

    # Unicidad por fecha
    exists = Feriado.query.filter(Feriado.fecha == fecha).first()
    if exists:
        flash(f"Ya existe un feriado registrado para la fecha {fecha.isoformat()}.", "warning")
        return redirect(url_for("feriados.editar", feriado_id=exists.id))

    f = Feriado(
        fecha=fecha,
        nombre=nombre,
        tipo=tipo,
        region=region,
        activo=activo,
    )

    db.session.add(f)
    db.session.commit()

    flash("Feriado creado correctamente.", "success")
    return redirect(url_for("feriados.listado", year=fecha.year))


@bp.get("/<int:feriado_id>/editar")
@login_required
@role_required("ADMIN")
def editar(feriado_id: int):
    f = Feriado.query.get_or_404(feriado_id)
    return render_template(
        "feriados/form.html",
        modo="editar",
        f=f,
        year=f.fecha.year if f.fecha else _year_or_default(None),
    )


@bp.post("/<int:feriado_id>/editar")
@login_required
@role_required("ADMIN")
def editar_post(feriado_id: int):
    f = Feriado.query.get_or_404(feriado_id)

    fecha_new = _parse_date(request.form.get("fecha"))
    nombre = (request.form.get("nombre") or "").strip()
    tipo = _tipo_norm(request.form.get("tipo"))
    region = (request.form.get("region") or "").strip() or None
    activo = (request.form.get("activo") or "").strip().lower() in {"1", "true", "on", "si", "sí"}

    if not fecha_new:
        flash("Debes indicar la fecha del feriado.", "danger")
        return redirect(url_for("feriados.editar", feriado_id=feriado_id))

    if not nombre:
        flash("Debes indicar el nombre/descripcion del feriado.", "danger")
        return redirect(url_for("feriados.editar", feriado_id=feriado_id))

    # Si cambia fecha, validar unicidad
    if fecha_new != f.fecha:
        exists = Feriado.query.filter(Feriado.fecha == fecha_new).first()
        if exists:
            flash(f"Ya existe un feriado registrado para la fecha {fecha_new.isoformat()}.", "danger")
            return redirect(url_for("feriados.editar", feriado_id=feriado_id))

    f.fecha = fecha_new
    f.nombre = nombre
    f.tipo = tipo
    f.region = region
    f.activo = activo

    db.session.commit()

    flash("Feriado actualizado correctamente.", "success")
    return redirect(url_for("feriados.listado", year=fecha_new.year))


@bp.post("/<int:feriado_id>/toggle")
@login_required
@role_required("ADMIN")
def toggle(feriado_id: int):
    """
    Activa/Desactiva un feriado (soft).
    """
    f = Feriado.query.get_or_404(feriado_id)
    f.activo = not bool(f.activo)
    db.session.commit()

    estado_txt = "activado" if f.activo else "desactivado"
    flash(f"Feriado {estado_txt}.", "success")
    y = f.fecha.year if f.fecha else _year_or_default(None)
    return redirect(url_for("feriados.listado", year=y))
