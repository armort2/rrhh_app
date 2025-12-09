# web/app/blueprints/core/routes.py

from flask import render_template, request
from sqlalchemy import or_

from ...extensions import db
from ...models import Trabajador, Obra

from . import bp


@bp.route("/")
def index():
    # Filtros antiguos
    q = request.args.get("q", type=str)
    obra_id = request.args.get("obra_id", type=int)
    estado = request.args.get("estado", type=str)

    # Filtros nuevos
    obra_nombre = request.args.get("obra", "", type=str).strip()
    cargo = request.args.get("cargo", "", type=str).strip()

    # Paginación
    page = request.args.get("page", 1, type=int)
    per_page = 25

    # Base query con join a Obra
    query = Trabajador.query.join(Obra)

    # 1) Filtro de búsqueda libre
    if q:
        texto = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Trabajador.rut.ilike(texto),
                Trabajador.nombres.ilike(texto),
                Trabajador.ap_paterno.ilike(texto),
                Trabajador.ap_materno.ilike(texto),
            )
        )

    # 2) Filtro por obra (ID)
    if obra_id:
        query = query.filter(Trabajador.obra_id == obra_id)

    # 3) Filtro por estado laboral
    if estado:
        query = query.filter(Trabajador.estado_trabajador == estado)

    # 4) Filtro nuevo: obra por nombre
    if obra_nombre:
        query = query.filter(Obra.nombre == obra_nombre)

    # 5) Filtro nuevo: cargo
    if cargo:
        query = query.filter(Trabajador.cargo == cargo)

    # Orden
    query = query.order_by(Obra.nombre, Trabajador.ap_paterno, Trabajador.ap_materno)

    # Resultados filtrados
    trabajadores_filtrados = query.all()
    total_registros = len(trabajadores_filtrados)

    # Paginación
    if total_registros == 0:
        total_pages = 1
        trabajadores_page = []
        page = 1
    else:
        total_pages = (total_registros + per_page - 1) // per_page

        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages

        start = (page - 1) * per_page
        end = start + per_page
        trabajadores_page = trabajadores_filtrados[start:end]

    # Lista de obras para filtros (solo nombres)
    obras_qs = (
        Obra.query
        .filter_by(estado="ACTIVA")
        .order_by(Obra.nombre)
        .all()
    )
    obras = [o.nombre for o in obras_qs]

    # Lista de cargos disponibles (solución correcta)
    cargos_rows = Trabajador.query.with_entities(Trabajador.cargo).distinct().all()
    cargos = sorted({row[0] for row in cargos_rows if row[0]})

    return render_template(
        "index.html",
        trabajadores=trabajadores_page,
        obras=obras,
        cargos=cargos,
        obra_seleccionada=obra_nombre,
        cargo_seleccionado=cargo,
        total_registros=total_registros,
        page=page,
        total_pages=total_pages,
        # Filtros antiguos
        filtro_q=q,
        filtro_obra_id=obra_id,
        filtro_estado=estado,
    )


@bp.route("/ping")
def ping():
    return {"status": "ok", "message": "RRHH app online 🤝"}
