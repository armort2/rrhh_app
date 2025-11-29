from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_


from .models import (
    Trabajador,
    Obra,
    AFP,
    Salud,
    Banco,
    CajaCompensacion,
    Cargo,
    Contrato,
    Empleador,
)
from . import db

main_bp = Blueprint("main", __name__)


# ---------- HOME / TRABAJADORES ----------

@main_bp.route("/")
def index():
    # Filtros desde la URL (?q=...&obra_id=...&estado=...)
    q = request.args.get("q", type=str)
    obra_id = request.args.get("obra_id", type=int)
    estado = request.args.get("estado", type=str)

    # Base query: siempre unimos con Obra para ordenar y mostrar
    query = Trabajador.query.join(Obra)

    # Filtro de texto: RUT / nombres / apellidos
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

    # Filtro por obra
    if obra_id:
        query = query.filter(Trabajador.obra_id == obra_id)

    # Filtro por estado laboral
    if estado:
        query = query.filter(Trabajador.estado_trabajador == estado)

    trabajadores = (
        query
        .order_by(Obra.nombre, Trabajador.ap_paterno, Trabajador.ap_materno)
        .all()
    )

    # Para el combo de obras en el filtro
    obras = (
        Obra.query
        .filter_by(estado="ACTIVA")
        .order_by(Obra.nombre)
        .all()
    )

    return render_template(
        "index.html",
        trabajadores=trabajadores,
        obras=obras,
        filtro_q=q,
        filtro_obra_id=obra_id,
        filtro_estado=estado,
    )


@main_bp.route("/contratos")
def lista_contratos():
    # Filtros desde la URL (?empleador_id=...&obra_id=...&estado=...)
    empleador_id = request.args.get("empleador_id", type=int)
    obra_id = request.args.get("obra_id", type=int)
    estado = request.args.get("estado", type=str)

    # Base query
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

@main_bp.route("/trabajadores/<int:trabajador_id>")
def detalle_trabajador(trabajador_id):
    trabajador = Trabajador.query.get_or_404(trabajador_id)
    return render_template("trabajador_detalle.html", trabajador=trabajador)

@main_bp.route("/contratos/<int:contrato_id>")
def contrato_detalle(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    return render_template("contrato_detalle.html", contrato=contrato)


# ---------- CONTRATOS ----------

@main_bp.route("/contratos/nuevo", methods=["GET", "POST"])
def nuevo_contrato():
    # Puede venir desde la ficha del trabajador: ?trabajador_id=123
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
                return redirect(url_for("main.index"))

    if request.method == "POST":
        # --- Validaciones básicas ---
        if not trabajador:
            flash("Debes seleccionar un trabajador válido para asociar el contrato.", "error")
            return redirect(url_for("main.nuevo_contrato"))

        empleador_id = request.form.get("empleador_id")
        obra_id = request.form.get("obra_id")
        cargo_id = request.form.get("cargo_id")
        tipo_contrato = request.form.get("tipo_contrato")
        fecha_inicio = _parse_date(request.form.get("fecha_inicio"))
        fecha_termino = _parse_date(request.form.get("fecha_termino"))

        jornada = request.form.get("jornada") or None
        horas_semanales = _parse_int(request.form.get("horas_semanales"))

        sueldo_base = _parse_decimal(request.form.get("sueldo_base"))
        asignacion_movilizacion = _parse_decimal(request.form.get("asignacion_movilizacion"))
        asignacion_colacion = _parse_decimal(request.form.get("asignacion_colacion"))
        asignacion_herramientas = _parse_decimal(request.form.get("asignacion_herramientas"))

                # ...

        estado_contrato = request.form.get("estado_contrato") or "VIGENTE"

        # --- Regla de negocio: un contrato vigente por trabajador + empleador ---
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
                return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))


        # Campos obligatorios mínimos
        if not empleador_id:
            flash("Debes seleccionar un empleador para el contrato.", "error")
            return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))

        if not obra_id:
            flash("Debes seleccionar una obra para el contrato.", "error")
            return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))

        if not cargo_id:
            flash("Debes seleccionar un cargo para este contrato.", "error")
            return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))

        if not tipo_contrato:
            flash("Debes indicar el tipo de contrato (indefinido, plazo fijo, faena, etc.).", "error")
            return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))

        if not fecha_inicio:
            flash("Debes indicar la fecha de inicio del contrato.", "error")
            return redirect(url_for("main.nuevo_contrato", trabajador_id=trabajador.id))

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
        # Volvemos a la ficha del trabajador, que ya muestra sus contratos
        return redirect(url_for("main.detalle_trabajador", trabajador_id=trabajador.id))

    # ========== GET ==========
    empleadores = Empleador.query.order_by(Empleador.razon_social).all()
    obras = Obra.query.filter_by(estado="ACTIVA").order_by(Obra.nombre).all()
    cargos = Cargo.query.order_by(Cargo.nombre).all()

    # Sugerencias por defecto
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

@main_bp.route("/ping")
def ping():
    return {"status": "ok", "message": "RRHH app online 🤝"}


# ---------- Helpers de parseo ----------

def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_int(value: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_decimal(value: str):
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


# ---------- NUEVO TRABAJADOR (FORMULARIO MAESTRO BÁSICO) ----------

@main_bp.route("/trabajadores/nuevo", methods=["GET", "POST"])
def nuevo_trabajador():
    if request.method == "POST":
        # --- Datos básicos obligatorios ---
        rut = request.form.get("rut")
        nombres = request.form.get("nombres")
        ap_paterno = request.form.get("ap_paterno")
        ap_materno = request.form.get("ap_materno")
        obra_id = request.form.get("obra_id")
        cargo_id = request.form.get("cargo_id")

        if not obra_id:
            flash("Debes seleccionar una obra.")
            return redirect(url_for("main.nuevo_trabajador"))

        if not cargo_id:
            flash("Debes seleccionar un cargo.")
            return redirect(url_for("main.nuevo_trabajador"))

        if not (rut and nombres and ap_paterno and ap_materno):
            flash("Completa todos los datos básicos del trabajador.")
            return redirect(url_for("main.nuevo_trabajador"))

        # --- Datos personales ---
        fecha_nacimiento = _parse_date(request.form.get("fecha_nacimiento"))
        nacionalidad = request.form.get("nacionalidad") or None
        sexo = request.form.get("sexo") or None
        estado_civil = request.form.get("estado_civil") or None

        # --- Contacto ---
        direccion = request.form.get("direccion") or None
        comuna = request.form.get("comuna") or None
        telefono = request.form.get("telefono") or None
        telefono_emergencia = request.form.get("telefono_emergencia") or None
        correo = request.form.get("correo") or None

        # --- Datos bancarios ---
        banco_id = request.form.get("banco_id") or None
        tipo_cuenta = request.form.get("tipo_cuenta") or None
        cuenta_numero = request.form.get("cuenta_numero") or None

        # Si es Cuenta RUT, el número de cuenta = RUT sin DV
        cuenta_rut = None
        if tipo_cuenta == "CTA_RUT":
            # Dejamos solo dígitos del RUT y quitamos el último (DV)
            solo_digitos = "".join(ch for ch in rut if ch.isdigit())
            if len(solo_digitos) >= 2:
                base = solo_digitos[:-1]  # sin DV
                cuenta_numero = base
                cuenta_rut = base
        else:
            # Para otros tipos no usamos cuenta_rut especial
            if not cuenta_numero:
                cuenta_numero = None

        # --- Pago a cuenta de tercero ---
        pago_tercero_activo = bool(request.form.get("pago_tercero_activo"))
        pago_tercero_rut = request.form.get("pago_tercero_rut") or None
        pago_tercero_nombre = request.form.get("pago_tercero_nombre") or None
        pago_tercero_banco_id = request.form.get("pago_tercero_banco_id") or None
        pago_tercero_tipo_cuenta = request.form.get("pago_tercero_tipo_cuenta") or None
        pago_tercero_cuenta_numero = request.form.get("pago_tercero_cuenta_numero") or None

        if not pago_tercero_activo:
            pago_tercero_rut = None
            pago_tercero_nombre = None
            pago_tercero_banco_id = None
            pago_tercero_tipo_cuenta = None
            pago_tercero_cuenta_numero = None

        # --- Previsional / Salud / Caja ---
        afp_id = request.form.get("afp_id")
        salud_id = request.form.get("salud_id")
        caja_compensacion_id = request.form.get("caja_compensacion_id")

        # Si es isapre, puede venir plan en UF
        uf_plan_salud = _parse_decimal(request.form.get("uf_plan_salud"))

        # --- APV ---
        apv_activo = bool(request.form.get("apv_activo"))
        apv_modalidad = request.form.get("apv_modalidad") or None
        apv_valor = _parse_decimal(request.form.get("apv_valor"))
        apv_institucion = request.form.get("apv_institucion") or None

        if not apv_activo:
            apv_modalidad = None
            apv_valor = None
            apv_institucion = None

        # --- CAV ---
        cav_activo = bool(request.form.get("cav_activo"))
        cav_modalidad = request.form.get("cav_modalidad") or None
        cav_valor = _parse_decimal(request.form.get("cav_valor"))
        cav_institucion = request.form.get("cav_institucion") or None

        if not cav_activo:
            cav_modalidad = None
            cav_valor = None
            cav_institucion = None

        # --- Cargas y condición especial ---
        num_cargas_familiares = _parse_int(request.form.get("num_cargas_familiares"))
        es_extranjero = bool(request.form.get("es_extranjero"))
        es_discapacitado = bool(request.form.get("es_discapacitado"))
        es_pensionado = bool(request.form.get("es_pensionado"))

        # --- Seguridad y salud ocupacional ---
        tiene_examen_preocupacional = bool(request.form.get("tiene_examen_preocupacional"))
        fecha_examen_preocupacional = _parse_date(request.form.get("fecha_examen_preocupacional"))
        tiene_curso_altura = bool(request.form.get("tiene_curso_altura"))
        fecha_vencimiento_curso_altura = _parse_date(request.form.get("fecha_vencimiento_curso_altura"))
        tiene_induccion_obra = bool(request.form.get("tiene_induccion_obra"))
        fecha_induccion_obra = _parse_date(request.form.get("fecha_induccion_obra"))

        # --- Laboral general ---
        estado_trabajador = request.form.get("estado_trabajador") or "VIGENTE"
        tipo_trabajador = request.form.get("tipo_trabajador") or None
        fecha_ingreso_empresa = _parse_date(request.form.get("fecha_ingreso_empresa"))
        fecha_egreso_empresa = _parse_date(request.form.get("fecha_egreso_empresa"))

        # Crear instancia del trabajador
        t = Trabajador(
            rut=rut,
            nombres=nombres,
            ap_paterno=ap_paterno,
            ap_materno=ap_materno,
            obra_id=int(obra_id),

            fecha_nacimiento=fecha_nacimiento,
            nacionalidad=nacionalidad,
            sexo=sexo,
            estado_civil=estado_civil,

            direccion=direccion,
            comuna=comuna,
            telefono=telefono,
            telefono_emergencia=telefono_emergencia,
            correo=correo,

            # Banco trabajador
            banco_id=int(banco_id) if banco_id else None,
            tipo_cuenta=tipo_cuenta,
            cuenta_rut=cuenta_rut,
            cuenta_numero=cuenta_numero,

            # Pago a tercero
            pago_tercero_activo=pago_tercero_activo,
            pago_tercero_rut=pago_tercero_rut,
            pago_tercero_nombre=pago_tercero_nombre,
            pago_tercero_banco_id=int(pago_tercero_banco_id) if pago_tercero_banco_id else None,
            pago_tercero_tipo_cuenta=pago_tercero_tipo_cuenta,
            pago_tercero_cuenta_numero=pago_tercero_cuenta_numero,

            afp_id=int(afp_id) if afp_id else None,
            salud_id=int(salud_id) if salud_id else None,
            caja_compensacion_id=int(caja_compensacion_id) if caja_compensacion_id else None,
            uf_plan_salud=uf_plan_salud,

            apv_activo=apv_activo,
            apv_modalidad=apv_modalidad,
            apv_valor=apv_valor,
            apv_institucion=apv_institucion,

            cav_activo=cav_activo,
            cav_modalidad=cav_modalidad,
            cav_valor=cav_valor,
            cav_institucion=cav_institucion,

            num_cargas_familiares=num_cargas_familiares,
            es_extranjero=es_extranjero,
            es_discapacitado=es_discapacitado,
            es_pensionado=es_pensionado,

            tiene_examen_preocupacional=tiene_examen_preocupacional,
            fecha_examen_preocupacional=fecha_examen_preocupacional,
            tiene_curso_altura=tiene_curso_altura,
            fecha_vencimiento_curso_altura=fecha_vencimiento_curso_altura,
            tiene_induccion_obra=tiene_induccion_obra,
            fecha_induccion_obra=fecha_induccion_obra,

            estado_trabajador=estado_trabajador,
            tipo_trabajador=tipo_trabajador,
            fecha_ingreso_empresa=fecha_ingreso_empresa,
            fecha_egreso_empresa=fecha_egreso_empresa,
        )

        db.session.add(t)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "No se pudo registrar el trabajador. "
                "Verifica que el RUT no esté ya registrado y revisa los datos ingresados.",
                "error",
            )
            return redirect(url_for("main.nuevo_trabajador"))

        flash("Trabajador registrado correctamente.")
        return redirect(url_for("main.index"))

    # GET
    obras = Obra.query.filter_by(estado="ACTIVA").order_by(Obra.nombre).all()
    if not obras:
        flash("Primero debes crear al menos una obra antes de registrar trabajadores.")
        return redirect(url_for("main.lista_obras"))

    bancos = Banco.query.order_by(Banco.nombre).all()
    afps = AFP.query.order_by(AFP.nombre).all()
    salud_list = Salud.query.order_by(Salud.nombre).all()
    cajas = CajaCompensacion.query.order_by(CajaCompensacion.nombre).all()
    cargos = Cargo.query.order_by(Cargo.id).all()

    return render_template(
        "nuevo_trabajador.html",
        obras=obras,
        bancos=bancos,
        afps=afps,
        salud_list=salud_list,
        cajas=cajas,
        cargos=cargos,
    )



# ---------- OBRAS ----------

@main_bp.route("/obras/")
def lista_obras():
    obras = Obra.query.order_by(Obra.nombre).all()
    return render_template("obras.html", obras=obras)


@main_bp.route("/obras/nueva", methods=["GET", "POST"])
def nueva_obra():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        codigo = request.form.get("codigo")
        centro_costo = request.form.get("centro_costo")
        comuna = request.form.get("comuna")
        estado = request.form.get("estado") or "ACTIVA"

        if not (nombre and codigo):
            flash("Nombre y código de la obra son obligatorios.")
            return redirect(url_for("main.nueva_obra"))

        o = Obra(
            nombre=nombre,
            codigo=codigo,
            centro_costo=centro_costo,
            comuna=comuna,
            estado=estado,
        )
        db.session.add(o)
        db.session.commit()

        flash("Obra creada correctamente.")
        return redirect(url_for("main.lista_obras"))

    return render_template("nueva_obra.html")
