# web/app/blueprints/contratos/routes.py

from flask import render_template, request, redirect, url_for, flash

from sqlalchemy import or_

from ...extensions import db
from ...models import Trabajador, Obra, Cargo, Contrato, Empleador
from ...utils import parse_date, parse_int, parse_decimal

from . import bp


@bp.route("/")
def lista_contratos():
    empleador_id = request.args.get("empleador_id", type=int)
    obra_id = request.args.get("obra_id", type=int)
    estado = request.args.get("estado", type=str)

    query = (
        Contrato.query
        .join(Trabajador)
        .join(Obra)
        .outerjoin(Empleador)
    )

    if empleador_id:
        query = query.filter(Contrato.empleador_id == empleador_id)

    if obra_id:
        query = query.filter(Contrato.obra_id == obra_id)

    if estado:
        query = query.filter(Contrato.estado_contrato == estado)

    contratos = (
        query
        .order_by(
            Obra.nombre,
            Trabajador.ap_paterno,
            Trabajador.ap_materno,
            Contrato.fecha_inicio.desc()
        )
        .all()
    )

    empleadores = Empleador.query.order_by(Empleador.razon_social).all()
    obras = Obra.query.order_by(Obra.nombre).all()

    return render_template(
        "contratos.html",
        contratos=contratos,
        empleadores=empleadores,
        obras=obras,
        filtro_empleador_id=empleador_id,
        filtro_obra_id=obra_id,
        filtro_estado=estado,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_contrato():
    trabajador_id_param = request.args.get("trabajador_id") or request.form.get("trabajador_id")

    trabajador = None
    if trabajador_id_param:
        try:
            trabajador_id_int = int(trabajador_id_param)
        except ValueError:
            trabajador_id_int = None

        if trabajador_id_int:
            trabajador = Trabajador.query.get(trabajador_id_int)
            if not trabajador:
                flash("No se encontró el trabajador indicado.", "error")
                return redirect(url_for("core.index"))

    if request.method == "POST":
        if not trabajador:
            flash("Debes seleccionar un trabajador válido para asociar el contrato.", "error")
            return redirect(url_for("contratos.nuevo_contrato"))

        empleador_id = request.form.get("empleador_id")
        obra_id = request.form.get("obra_id")
        cargo_id = request.form.get("cargo_id")
        tipo_contrato = request.form.get("tipo_contrato")
        fecha_inicio = parse_date(request.form.get("fecha_inicio"))
        fecha_termino = parse_date(request.form.get("fecha_termino"))

        jornada = request.form.get("jornada") or None
        horas_semanales = parse_int(request.form.get("horas_semanales"))

        sueldo_base = parse_decimal(request.form.get("sueldo_base"))
        asignacion_movilizacion = parse_decimal(request.form.get("asignacion_movilizacion"))
        asignacion_colacion = parse_decimal(request.form.get("asignacion_colacion"))
        asignacion_herramientas = parse_decimal(request.form.get("asignacion_herramientas"))

        estado_contrato = request.form.get("estado_contrato") or "VIGENTE"

        # Regla: un contrato VIGENTE por trabajador+empleador
        if estado_contrato == "VIGENTE":
            contrato_vigente = (
                Contrato.query
                .filter(
                    Contrato.trabajador_id == trabajador.id,
                    Contrato.empleador_id == int(empleador_id),
                    Contrato.estado_contrato == "VIGENTE",
                )
                .first()
            )
            if contrato_vigente:
                flash(
                    "Este trabajador ya tiene un contrato VIGENTE con el empleador seleccionado. "
                    "Primero debes terminar ese contrato antes de crear uno nuevo.",
                    "error",
                )
                return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

        if not empleador_id:
            flash("Debes seleccionar un empleador para el contrato.", "error")
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        if not obra_id:
            flash("Debes seleccionar una obra para el contrato.", "error")
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        if not cargo_id:
            flash("Debes seleccionar un cargo para este contrato.", "error")
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        if not tipo_contrato:
            flash("Debes indicar el tipo de contrato (indefinido, plazo fijo, faena, etc.).", "error")
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        if not fecha_inicio:
            flash("Debes indicar la fecha de inicio del contrato.", "error")
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        contrato = Contrato(
            trabajador_id=trabajador.id,
            empleador_id=int(empleador_id),
            obra_id=int(obra_id),
            cargo_id=int(cargo_id),

            tipo_contrato=tipo_contrato,
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,

            jornada=jornada,
            horas_semanales=horas_semanales,

            sueldo_base=sueldo_base,
            asignacion_movilizacion=asignacion_movilizacion,
            asignacion_colacion=asignacion_colacion,
            asignacion_herramientas=asignacion_herramientas,

            estado_contrato=estado_contrato,
        )

        db.session.add(contrato)
        db.session.commit()

        flash("Contrato creado correctamente.", "success")
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    # GET
    empleadores = Empleador.query.order_by(Empleador.razon_social).all()
    obras = Obra.query.filter_by(estado="ACTIVA").order_by(Obra.nombre).all()
    cargos = Cargo.query.order_by(Cargo.nombre).all()

    empleador_default_id = None
    obra_default_id = None

    if trabajador:
        if trabajador.obra:
            obra_default_id = trabajador.obra.id
            if trabajador.obra.empleador_id:
                empleador_default_id = trabajador.obra.empleador_id

    return render_template(
        "nuevo_contrato.html",
        trabajador=trabajador,
        empleadores=empleadores,
        obras=obras,
        cargos=cargos,
        empleador_default_id=empleador_default_id,
        obra_default_id=obra_default_id,
    )


@bp.route("/<int:contrato_id>")
def contrato_detalle(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    return render_template("contrato_detalle.html", contrato=contrato)
