# web/app/blueprints/obras/routes.py

from __future__ import annotations

from datetime import datetime, date

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from ...extensions import db
from ...models import Obra
from ...auth.decorators import role_required
from . import bp


# ---------------------------
# Helpers
# ---------------------------
def _parse_date(value: str | None):
    """
    Convierte 'YYYY-MM-DD' a date. Si viene vacío o inválido, retorna None.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _s(val: str | None, *, lower: bool = False) -> str | None:
    """
    Normaliza strings: strip + None si vacío.
    """
    if val is None:
        return None
    out = val.strip()
    if not out:
        return None
    return out.lower() if lower else out


# ---------------------------
# Routes
# ---------------------------
@bp.route("/")
@login_required
def lista_obras():
    obras = (
        Obra.query
        .order_by((Obra.estado == "ACTIVA").desc(), Obra.nombre.asc())
        .all()
    )
    return render_template("obras/obras.html", obras=obras)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def nueva_obra():
    if request.method == "POST":
        nombre = _s(request.form.get("nombre"))
        codigo = _s(request.form.get("codigo"))

        centro_costo = _s(request.form.get("centro_costo"))
        direccion = _s(request.form.get("direccion"))
        comuna = _s(request.form.get("comuna"))

        # Contacto administrativo
        admin_nombre = _s(request.form.get("obra_administrativo_nombre"))
        admin_rut = _s(request.form.get("obra_administrativo_rut"))
        admin_telefono = _s(request.form.get("obra_administrativo_telefono"))
        admin_correo = _s(request.form.get("obra_administrativo_correo"), lower=True)
        admin_cargo = _s(request.form.get("obra_administrativo_cargo"))

        estado = (request.form.get("estado") or "ACTIVA").strip() or "ACTIVA"
        if estado not in ("ACTIVA", "CERRADA"):
            flash("Estado inválido.", "danger")
            return redirect(url_for("obras.nueva_obra"))

        fecha_inicio = _parse_date(request.form.get("fecha_inicio"))
        fecha_cierre = _parse_date(request.form.get("fecha_cierre"))

        if estado == "CERRADA":
            fecha_cierre = fecha_cierre or date.today()
        else:
            fecha_cierre = None

        if not (nombre and codigo):
            flash("Nombre y código de la obra son obligatorios.", "warning")
            return redirect(url_for("obras.nueva_obra"))

        o = Obra(
            nombre=nombre,
            codigo=codigo,
            centro_costo=centro_costo,
            direccion=direccion,
            comuna=comuna,
            estado=estado,
            fecha_inicio=fecha_inicio,
            fecha_cierre=fecha_cierre,

            obra_administrativo_nombre=admin_nombre,
            obra_administrativo_rut=admin_rut,
            obra_administrativo_telefono=admin_telefono,
            obra_administrativo_correo=admin_correo,
            obra_administrativo_cargo=admin_cargo,
        )
        db.session.add(o)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("No se pudo crear: verifica que el código no esté repetido.", "danger")
            return redirect(url_for("obras.nueva_obra"))

        flash("Obra creada correctamente.", "success")
        return redirect(url_for("obras.lista_obras"))

    return render_template("obras/nueva_obra.html")


@bp.route("/<int:obra_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def editar_obra(obra_id: int):
    obra = Obra.query.get_or_404(obra_id)

    if request.method == "POST":
        codigo = _s(request.form.get("codigo"))
        nombre = _s(request.form.get("nombre"))

        if not (nombre and codigo):
            flash("Nombre y código son obligatorios.", "warning")
            return redirect(url_for("obras.editar_obra", obra_id=obra.id))

        estado = (request.form.get("estado") or obra.estado or "ACTIVA").strip() or "ACTIVA"
        if estado not in ("ACTIVA", "CERRADA"):
            flash("Estado inválido.", "danger")
            return redirect(url_for("obras.editar_obra", obra_id=obra.id))

        fecha_inicio = _parse_date(request.form.get("fecha_inicio"))
        fecha_cierre = _parse_date(request.form.get("fecha_cierre"))

        if estado == "CERRADA":
            fecha_cierre = fecha_cierre or date.today()
        else:
            fecha_cierre = None

        obra.codigo = codigo
        obra.nombre = nombre

        obra.centro_costo = _s(request.form.get("centro_costo"))
        obra.direccion = _s(request.form.get("direccion"))
        obra.comuna = _s(request.form.get("comuna"))

        # Contacto administrativo
        obra.obra_administrativo_nombre = _s(request.form.get("obra_administrativo_nombre"))
        obra.obra_administrativo_rut = _s(request.form.get("obra_administrativo_rut"))
        obra.obra_administrativo_telefono = _s(request.form.get("obra_administrativo_telefono"))
        obra.obra_administrativo_correo = _s(request.form.get("obra_administrativo_correo"), lower=True)
        obra.obra_administrativo_cargo = _s(request.form.get("obra_administrativo_cargo"))

        obra.estado = estado
        obra.fecha_inicio = fecha_inicio
        obra.fecha_cierre = fecha_cierre

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("No se pudo guardar. Revisa si el código ya existe en otra obra.", "danger")
            return redirect(url_for("obras.editar_obra", obra_id=obra.id))

        flash("Obra actualizada correctamente.", "success")
        return redirect(url_for("obras.editar_obra", obra_id=obra.id))

    return render_template("obras/obras_editar.html", obra=obra)


@bp.post("/<int:obra_id>/toggle-estado")
@login_required
@role_required("ADMIN")
def toggle_estado(obra_id: int):
    obra = Obra.query.get_or_404(obra_id)

    if obra.estado == "ACTIVA":
        obra.estado = "CERRADA"
        obra.fecha_cierre = obra.fecha_cierre or date.today()
        flash("Obra cerrada correctamente.", "warning")
    else:
        obra.estado = "ACTIVA"
        obra.fecha_cierre = None
        flash("Obra reactivada correctamente.", "success")

    db.session.commit()
    return redirect(request.referrer or url_for("obras.lista_obras"))