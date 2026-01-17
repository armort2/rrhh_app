# web/app/blueprints/core/routes.py

from __future__ import annotations

from datetime import date, timedelta
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_, func

from ...extensions import db
from ...models import Trabajador, Obra, Cargo, Contrato
from ...auth.decorators import role_required

from . import bp


@bp.route("/")
@login_required
def index():
    # KPIs base
    trabajadores_total = db.session.query(func.count(Trabajador.id)).scalar() or 0

    # Obras activas
    obras_activas = (
        db.session.query(func.count(Obra.id))
        .filter(Obra.estado == "ACTIVA")
        .scalar()
        or 0
    )

    hoy = date.today()

    # Contratos vigentes / por vencer (solo si el modelo tiene campos)
    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        contratos_vigentes = (
            db.session.query(func.count(Contrato.id))
            .filter(
                Contrato.fecha_inicio <= hoy,
                or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy),
            )
            .scalar()
            or 0
        )

        limite = hoy + timedelta(days=30)
        contratos_por_vencer_30d = (
            db.session.query(func.count(Contrato.id))
            .filter(
                Contrato.fecha_termino.isnot(None),
                Contrato.fecha_termino >= hoy,
                Contrato.fecha_termino <= limite,
            )
            .scalar()
            or 0
        )
    else:
        contratos_vigentes = 0
        contratos_por_vencer_30d = 0

    kpis = {
        "trabajadores_total": trabajadores_total,
        "obras_activas": obras_activas,
        "contratos_vigentes": contratos_vigentes,
        "contratos_por_vencer_30d": contratos_por_vencer_30d,
    }

    return render_template("index.html", kpis=kpis)


@bp.route("/ping")
def ping():
    return {"status": "ok", "message": "RRHH app online 🤝"}


# -------------------------------------------------------------------
# MÓDULO: Cargos (catálogo)
# -------------------------------------------------------------------

@bp.get("/cargos")
@login_required
@role_required("ADMIN")
def cargos_listado():
    """
    Listado administrable de cargos.
    - Búsqueda por: id (exacto), nombre, categoria, descripcion
    - Filtro por estado (si existe Cargo.activo): activos / inactivos / todos
    """
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "activos").strip().lower()  # activos|inactivos|todos

    query = Cargo.query

    # Filtro por texto/ID
    if q:
        if q.isdigit():
            query = query.filter(Cargo.id == int(q))
        else:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Cargo.nombre.ilike(like),
                    Cargo.categoria.ilike(like),
                    Cargo.descripcion.ilike(like),
                )
            )

    # Filtro por "activo" solo si existe la columna/atributo
    if hasattr(Cargo, "activo"):
        if estado == "activos":
            query = query.filter(Cargo.activo.is_(True))
        elif estado == "inactivos":
            query = query.filter(Cargo.activo.is_(False))
    else:
        estado = "todos"

    cargos = query.order_by(Cargo.id.asc()).all()

    return render_template(
        "cargos/cargos_listado.html",
        cargos=cargos,
        q=q,
        estado=estado,
        soporta_activo=hasattr(Cargo, "activo"),
    )


@bp.post("/cargos/crear")
@login_required
@role_required("ADMIN")
def cargo_crear():
    q = (request.form.get("q") or "").strip()
    estado = (request.form.get("estado") or "activos").strip().lower()

    nombre = (request.form.get("nombre") or "").strip()
    categoria = (request.form.get("categoria") or "").strip() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    if not nombre:
        flash("Debes ingresar el nombre del cargo.", "error")
        return redirect(url_for("core.cargos_listado", q=q, estado=estado))

    existente = Cargo.query.filter(Cargo.nombre.ilike(nombre)).first()
    if existente:
        flash(f"Ya existe un cargo con el nombre '{existente.nombre}'.", "warning")
        return redirect(url_for("core.cargos_listado", q=q, estado=estado))

    nuevo = Cargo(
        nombre=nombre,
        categoria=categoria,
        descripcion=descripcion,
    )

    if hasattr(Cargo, "activo"):
        nuevo.activo = True

    db.session.add(nuevo)
    db.session.commit()

    flash("Cargo agregado correctamente.", "success")
    return redirect(url_for("core.cargos_listado", q=q, estado=estado))


@bp.post("/cargos/<int:cargo_id>/editar")
@login_required
@role_required("ADMIN")
def cargo_editar(cargo_id: int):
    cargo = Cargo.query.get_or_404(cargo_id)

    nombre = (request.form.get("nombre") or "").strip()
    categoria = (request.form.get("categoria") or "").strip() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    if not nombre:
        flash("El nombre del cargo no puede quedar vacío.", "error")
        return redirect(url_for("core.cargos_listado", q=request.form.get("q", ""), estado=request.form.get("estado", "activos")))

    cargo.nombre = nombre
    cargo.categoria = categoria
    cargo.descripcion = descripcion

    db.session.commit()
    flash("Cargo actualizado correctamente.", "success")

    return redirect(url_for("core.cargos_listado", q=request.form.get("q", ""), estado=request.form.get("estado", "activos")))


@bp.post("/cargos/<int:cargo_id>/toggle")
@login_required
@role_required("ADMIN")
def cargo_toggle_activo(cargo_id: int):
    """
    Baja lógica (soft delete) / reactivación.
    Requiere que exista Cargo.activo (columna en BD + atributo en modelo).
    """
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "activos").strip().lower()

    if not hasattr(Cargo, "activo"):
        flash(
            "Este sistema aún no tiene 'activo' en cargos. Agrega la columna para habilitar baja lógica.",
            "warning",
        )
        return redirect(url_for("core.cargos_listado", q=q, estado=estado))

    cargo = Cargo.query.get_or_404(cargo_id)
    cargo.activo = not cargo.activo
    db.session.commit()

    flash(
        f"Cargo '{cargo.nombre}' actualizado: {'Activo' if cargo.activo else 'Inactivo'}.",
        "success",
    )

    return redirect(url_for("core.cargos_listado", q=q, estado=estado))


# Si no lo usas, recomiendo borrarlo y depender solo de role_required.
def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if getattr(current_user, "is_admin", False):
            return fn(*args, **kwargs)

        roles = []
        if hasattr(current_user, "roles") and current_user.roles:
            roles = [getattr(r, "nombre", None) or getattr(r, "name", None) for r in current_user.roles]
        if "ADMIN" in roles:
            return fn(*args, **kwargs)

        abort(403)

    return wrapper
