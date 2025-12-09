# web/app/blueprints/trabajadores/routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import (
    Trabajador,
    Obra,
    AFP,
    Salud,
    Banco,
    CajaCompensacion,
    Cargo,
    Contrato,   # 👈 IMPORTANTE: para listar contratos del trabajador
)
from ...utils import parse_date, parse_int, parse_decimal

# Blueprint de trabajadores
bp = Blueprint("trabajadores", __name__, url_prefix="/trabajadores")


# ===========================
# FICHA (DETALLE) TRABAJADOR
# ===========================
@bp.route("/<int:trabajador_id>", methods=["GET"])
def detalle_trabajador(trabajador_id):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    # Contratos asociados a este trabajador
    contratos = (
        Contrato.query
        .filter_by(trabajador_id=trabajador.id)
        .order_by(Contrato.id.desc())
        .all()
    )

    return render_template(
        "trabajador_detalle.html",
        trabajador=trabajador,
        contratos=contratos,
    )


# ===========================
# EDITAR TRABAJADOR
# ===========================
@bp.route("/<int:trabajador_id>/editar", methods=["GET", "POST"])
def editar_trabajador(trabajador_id):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    if request.method == "POST":
        # --- Datos básicos obligatorios ---
        rut = request.form.get("rut")
        nombres = request.form.get("nombres")
        ap_paterno = request.form.get("ap_paterno")
        ap_materno = request.form.get("ap_materno")
        obra_id = request.form.get("obra_id")
        cargo_id = request.form.get("cargo_id")

        if not obra_id:
            flash("Debes seleccionar una obra.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        if not cargo_id:
            flash("Debes seleccionar un cargo.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        if not (rut and nombres and ap_paterno and ap_materno):
            flash("Completa todos los datos básicos del trabajador.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        # --- Datos personales ---
        fecha_nacimiento = parse_date(request.form.get("fecha_nacimiento"))
        nacionalidad = request.form.get("nacionalidad") or None
        sexo = request.form.get("sexo") or None
        estado_civil = request.form.get("estado_civil") or None

        # --- Contacto ---
        direccion = request.form.get("direccion") or None
        comuna = request.form.get("comuna") or None
        telefono = request.form.get("telefono") or None
        telefono_emergencia = request.form.get("telefono_emergencia") or None
        correo = request.form.get("correo") or None

        # --- Previsional / Salud / Caja ---
        afp_id = request.form.get("afp_id")
        salud_id = request.form.get("salud_id")
        caja_compensacion_id = request.form.get("caja_compensacion_id")

        # --- Laboral general ---
        estado_trabajador = request.form.get("estado_trabajador") or "VIGENTE"
        tipo_trabajador = request.form.get("tipo_trabajador") or None
        fecha_ingreso_empresa = parse_date(request.form.get("fecha_ingreso_empresa"))
        fecha_egreso_empresa = parse_date(request.form.get("fecha_egreso_empresa"))

        # Asignar al objeto existente
        trabajador.rut = rut
        trabajador.nombres = nombres
        trabajador.ap_paterno = ap_paterno
        trabajador.ap_materno = ap_materno
        trabajador.obra_id = int(obra_id)

        trabajador.fecha_nacimiento = fecha_nacimiento
        trabajador.nacionalidad = nacionalidad
        trabajador.sexo = sexo
        trabajador.estado_civil = estado_civil

        trabajador.direccion = direccion
        trabajador.comuna = comuna
        trabajador.telefono = telefono
        trabajador.telefono_emergencia = telefono_emergencia
        trabajador.correo = correo

        trabajador.afp_id = int(afp_id) if afp_id else None
        trabajador.salud_id = int(salud_id) if salud_id else None
        trabajador.caja_compensacion_id = int(caja_compensacion_id) if caja_compensacion_id else None

        trabajador.estado_trabajador = estado_trabajador
        trabajador.tipo_trabajador = tipo_trabajador
        trabajador.fecha_ingreso_empresa = fecha_ingreso_empresa
        trabajador.fecha_egreso_empresa = fecha_egreso_empresa

        # Cargo actual
        trabajador.cargo_id = int(cargo_id) if cargo_id else None

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "No se pudo actualizar el trabajador. "
                "Verifica que el RUT no esté duplicado y revisa los datos ingresados.",
                "error",
            )
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        flash("Datos del trabajador actualizados correctamente.", "success")
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    # GET: cargar datos para el formulario
    obras = Obra.query.filter_by(estado="ACTIVA").order_by(Obra.nombre).all()
    bancos = Banco.query.order_by(Banco.nombre).all()
    afps = AFP.query.order_by(AFP.nombre).all()
    salud_list = Salud.query.order_by(Salud.nombre).all()
    cajas = CajaCompensacion.query.order_by(CajaCompensacion.nombre).all()
    cargos = Cargo.query.order_by(Cargo.id).all()

    return render_template(
        "trabajador_editar.html",
        trabajador=trabajador,
        obras=obras,
        bancos=bancos,
        afps=afps,
        salud_list=salud_list,
        cajas=cajas,
        cargos=cargos,
    )


# ===========================
# NUEVO TRABAJADOR
# ===========================
@bp.route("/nuevo", methods=["GET", "POST"])
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
            return redirect(url_for("trabajadores.nuevo_trabajador"))

        if not cargo_id:
            flash("Debes seleccionar un cargo.")
            return redirect(url_for("trabajadores.nuevo_trabajador"))

        if not (rut and nombres and ap_paterno and ap_materno):
            flash("Completa todos los datos básicos del trabajador.")
            return redirect(url_for("trabajadores.nuevo_trabajador"))

        # --- Datos personales ---
        fecha_nacimiento = parse_date(request.form.get("fecha_nacimiento"))
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
            solo_digitos = "".join(ch for ch in rut if ch.isdigit())
            if len(solo_digitos) >= 2:
                base = solo_digitos[:-1]  # sin DV
                cuenta_numero = base
                cuenta_rut = base
        else:
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

        uf_plan_salud = parse_decimal(request.form.get("uf_plan_salud"))

        # --- APV ---
        apv_activo = bool(request.form.get("apv_activo"))
        apv_modalidad = request.form.get("apv_modalidad") or None
        apv_valor = parse_decimal(request.form.get("apv_valor"))
        apv_institucion = request.form.get("apv_institucion") or None

        if not apv_activo:
            apv_modalidad = None
            apv_valor = None
            apv_institucion = None

        # --- CAV ---
        cav_activo = bool(request.form.get("cav_activo"))
        cav_modalidad = request.form.get("cav_modalidad") or None
        cav_valor = parse_decimal(request.form.get("cav_valor"))
        cav_institucion = request.form.get("cav_institucion") or None

        if not cav_activo:
            cav_modalidad = None
            cav_valor = None
            cav_institucion = None

        # --- Cargas y condición especial ---
        num_cargas_familiares = parse_int(request.form.get("num_cargas_familiares"))
        es_extranjero = bool(request.form.get("es_extranjero"))
        es_discapacitado = bool(request.form.get("es_discapacitado"))
        es_pensionado = bool(request.form.get("es_pensionado"))

        # --- Seguridad y salud ocupacional ---
        tiene_examen_preocupacional = bool(request.form.get("tiene_examen_preocupacional"))
        fecha_examen_preocupacional = parse_date(request.form.get("fecha_examen_preocupacional"))
        tiene_curso_altura = bool(request.form.get("tiene_curso_altura"))
        fecha_vencimiento_curso_altura = parse_date(request.form.get("fecha_vencimiento_curso_altura"))
        tiene_induccion_obra = bool(request.form.get("tiene_induccion_obra"))
        fecha_induccion_obra = parse_date(request.form.get("fecha_induccion_obra"))

        # --- Laboral general ---
        estado_trabajador = request.form.get("estado_trabajador") or "VIGENTE"
        tipo_trabajador = request.form.get("tipo_trabajador") or None
        fecha_ingreso_empresa = parse_date(request.form.get("fecha_ingreso_empresa"))
        fecha_egreso_empresa = parse_date(request.form.get("fecha_egreso_empresa"))

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

            banco_id=int(banco_id) if banco_id else None,
            tipo_cuenta=tipo_cuenta,
            cuenta_rut=cuenta_rut,
            cuenta_numero=cuenta_numero,

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
            return redirect(url_for("trabajadores.nuevo_trabajador"))

        flash("Trabajador registrado correctamente.")
        return redirect(url_for("core.index"))

    # GET
    obras = Obra.query.filter_by(estado="ACTIVA").order_by(Obra.nombre).all()
    if not obras:
        flash("Primero debes crear al menos una obra antes de registrar trabajadores.")
        return redirect(url_for("obras.lista_obras"))

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
