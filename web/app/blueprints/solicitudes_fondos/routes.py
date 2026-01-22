# web/app/blueprints/solicitudes_fondos/routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List

import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ...auth.decorators import role_required
from ...extensions import db
from ...models import Obra, SolicitudFondos, SolicitudFondosItem, Tercero, Trabajador
from . import bp

SECCIONES = [
    ("REMU", "Remuneraciones"),
    ("REND", "Rendiciones de gastos"),
    ("TERC", "Contratistas y Proveedores"),
    ("VAR", "Pagos varios"),
]

ESTADOS = ["BORRADOR", "ENVIADA", "APROBADA", "RECHAZADA", "PAGADA"]
PERIODOS = [("QUINCENA", "Quincena"), ("FIN_MES", "Fin de mes"), ("OTRO", "Otro")]


# ---------------------------
# Accesos (scope = Centro de Costo)
# ---------------------------
def _obras_accesibles() -> List[Obra]:
    q = Obra.query
    if current_user.has_role("ADMIN"):
        return q.order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc()).all()

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return []
    return (
        q.filter(Obra.id.in_(obra_ids))
        .order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc())
        .all()
    )


def _centros_costos_accesibles() -> List[str]:
    obras = _obras_accesibles()
    ccs = sorted({(o.centro_costo or "").strip() for o in obras if (o.centro_costo or "").strip()})
    return ccs


def _assert_access_cc(centro_costo: str) -> None:
    if current_user.has_role("ADMIN"):
        return
    cc = (centro_costo or "").strip()
    if not cc or cc not in _centros_costos_accesibles():
        abort(403)


# ---------------------------
# Helpers negocio
# ---------------------------
def _next_numero_por_cc(centro_costo: str) -> int:
    max_num = (
        db.session.query(sa.func.max(SolicitudFondos.numero))
        .filter(SolicitudFondos.centro_costo == centro_costo)
        .scalar()
    )
    return int(max_num or 0) + 1


def _totales_por_seccion(items: List[SolicitudFondosItem]) -> Dict[str, Decimal]:
    tot: Dict[str, Decimal] = {k: Decimal("0.00") for k, _ in SECCIONES}
    for it in items:
        tot[it.seccion] = (tot.get(it.seccion, Decimal("0.00")) + (it.monto or 0))
    return tot


def _badge_class_estado(estado: str) -> str:
    e = (estado or "").upper().strip()
    if e in ("APROBADA", "PAGADA"):
        return "badge-success"
    if e in ("RECHAZADA",):
        return "badge-danger"
    if e in ("ENVIADA",):
        return "badge-info"
    return "badge-muted"


def _to_decimal_money(v) -> Decimal:
    """
    Convierte valores tipo dinero a Decimal("0.00") de forma tolerante.
    Acepta Decimal, int/float, str con separadores y símbolo $.
    Maneja casos:
      - "750000"
      - "750.000"
      - "750000.00"
      - "750.000,00"
      - "$ 750.000"
    """
    try:
        if v is None:
            return Decimal("0.00")
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))

        s = str(v).strip()
        if not s:
            return Decimal("0.00")

        s = s.replace("$", "").replace(" ", "")

        has_dot = "." in s
        has_comma = "," in s

        if has_dot and has_comma:
            # asume dot miles y comma decimal
            s = s.replace(".", "").replace(",", ".")
            return Decimal(s)

        if has_comma and not has_dot:
            # "1234,56"
            s = s.replace(",", ".")
            return Decimal(s)

        if has_dot and not has_comma:
            # Puede ser miles "1.234.567" o decimal "750000.00"
            parts = s.split(".")
            if len(parts) >= 3:
                # múltiples puntos => miles
                s = "".join(parts)
                return Decimal(s)

            # un solo punto: decimal o miles (si el grupo derecho es de 3)
            left, right = s.split(".", 1)
            if right.isdigit() and len(right) == 3 and left.isdigit():
                s = s.replace(".", "")
                return Decimal(s)

            # decimal (ej: "750000.00")
            return Decimal(s)

        return Decimal(s)
    except Exception:
        return Decimal("0.00")


def _assert_editable_solicitud(s: SolicitudFondos) -> bool:
    """
    En esta pantalla, solo permitimos edición cuando la solicitud está en BORRADOR.
    """
    if (s.estado or "").upper().strip() != "BORRADOR":
        flash("La solicitud no es editable porque su estado no es BORRADOR.", "warning")
        return False
    return True


# ---------------------------
# Listado
# ---------------------------
@bp.get("/")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    centros_costos = _centros_costos_accesibles()

    cc = (request.args.get("centro_costo") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    desde = request.args.get("desde") or ""
    hasta = request.args.get("hasta") or ""

    q = SolicitudFondos.query

    if not current_user.has_role("ADMIN"):
        if not centros_costos:
            q = q.filter(sa.text("1=0"))
        else:
            q = q.filter(SolicitudFondos.centro_costo.in_(centros_costos))

    if cc:
        _assert_access_cc(cc)
        q = q.filter(SolicitudFondos.centro_costo == cc)

    if estado in ESTADOS:
        q = q.filter(SolicitudFondos.estado == estado)

    try:
        if desde:
            d = datetime.strptime(desde, "%Y-%m-%d").date()
            q = q.filter(SolicitudFondos.fecha_solicitud >= d)
        if hasta:
            h = datetime.strptime(hasta, "%Y-%m-%d").date()
            q = q.filter(SolicitudFondos.fecha_solicitud <= h)
    except ValueError:
        flash("Rango de fechas inválido.", "warning")

    solicitudes = q.order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc()).all()

    return render_template(
        "solicitudes_fondos/listado.html",
        centros_costos=centros_costos,
        solicitudes=solicitudes,
        centro_costo=cc,
        estado=estado,
        desde=desde,
        hasta=hasta,
        estados=ESTADOS,
        badge_estado=_badge_class_estado,
    )


# ---------------------------
# Nueva
# ---------------------------
@bp.route("/nueva", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def nueva():
    centros_costos = _centros_costos_accesibles()
    obras = _obras_accesibles()

    if not centros_costos and not current_user.has_role("ADMIN"):
        flash("No tienes centros de costo disponibles (no hay obras asignadas).", "warning")
        return redirect(url_for("solicitudes_fondos.listado"))

    if request.method == "POST":
        cc = (request.form.get("centro_costo") or "").strip()
        if not cc:
            flash("Debes seleccionar un Centro de Costo.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        _assert_access_cc(cc)

        obra_id = request.form.get("obra_id", type=int)
        if obra_id:
            obra = Obra.query.get(obra_id)
            if not obra or (obra.centro_costo or "").strip() != cc:
                flash("Obra de referencia inválida para el Centro de Costo seleccionado.", "warning")
                return redirect(url_for("solicitudes_fondos.nueva"))

        numero = request.form.get("numero", type=int)
        fecha_solicitud_str = request.form.get("fecha_solicitud") or ""
        periodo_tipo = (request.form.get("periodo_tipo") or "").strip().upper()
        periodo_desde_str = request.form.get("periodo_desde") or ""
        periodo_hasta_str = request.form.get("periodo_hasta") or ""
        observaciones = (request.form.get("observaciones") or "").strip() or None

        try:
            fecha_solicitud = datetime.strptime(fecha_solicitud_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Fecha de solicitud inválida.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        if periodo_tipo not in dict(PERIODOS):
            flash("Tipo de período inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        periodo_desde = None
        periodo_hasta = None
        try:
            if periodo_desde_str:
                periodo_desde = datetime.strptime(periodo_desde_str, "%Y-%m-%d").date()
            if periodo_hasta_str:
                periodo_hasta = datetime.strptime(periodo_hasta_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Período desde/hasta inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        if not numero:
            numero = _next_numero_por_cc(cc)

        s = SolicitudFondos(
            centro_costo=cc,
            obra_id=obra_id or None,
            numero=numero,
            fecha_solicitud=fecha_solicitud,
            periodo_tipo=periodo_tipo,
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
            estado="BORRADOR",
            observaciones=observaciones,
            creado_por_user_id=current_user.id,
        )
        db.session.add(s)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("No se pudo crear la solicitud (¿número duplicado para el Centro de Costo?).", "danger")
            return redirect(url_for("solicitudes_fondos.nueva"))

        flash("Solicitud creada en estado BORRADOR.", "success")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    return render_template(
        "solicitudes_fondos/nueva.html",
        centros_costos=centros_costos,
        obras=obras,
        periodos=PERIODOS,
        hoy=date.today().strftime("%Y-%m-%d"),
    )


# ---------------------------
# Detalle
# ---------------------------
@bp.get("/<int:solicitud_id>")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    items = list(s.items or [])
    tot = _totales_por_seccion(items)

    obras_cc = (
        Obra.query.filter(Obra.centro_costo == s.centro_costo)
        .order_by(Obra.nombre.asc())
        .all()
    )

    terceros = (
        Tercero.query.filter(Tercero.estado == "VIGENTE")
        .order_by(Tercero.ap_paterno.asc())
        .limit(500)
        .all()
    )
    trabajadores = (
        Trabajador.query.filter(Trabajador.estado_trabajador == "VIGENTE")
        .order_by(Trabajador.ap_paterno.asc())
        .limit(500)
        .all()
    )

    resumen_anticipos = None
    if (s.periodo_tipo or "").upper().strip() == "QUINCENA":
        ref_date = s.periodo_desde or s.fecha_solicitud
        try:
            from ...services.anticipos_reader import get_resumen_anticipos_para_quincena  # noqa

            resumen_anticipos = get_resumen_anticipos_para_quincena(
                centro_costo=(s.centro_costo or "").strip(),
                anio=int(ref_date.year),
                mes=int(ref_date.month),
            )
        except Exception:
            resumen_anticipos = None

    if resumen_anticipos:
        remu_total = _to_decimal_money(getattr(resumen_anticipos, "total_monto", None))
        tot["REMU"] = remu_total

    total_general = sum(tot.values()) if tot else Decimal("0.00")

    # Ajuste: solo lectura también cuando el estado no es BORRADOR (salvo ADMIN/OPERADOR vean igual)
    # El template ya entiende "solo_lectura"; aquí lo reforzamos con estado.
    solo_lectura = current_user.has_role("REVISOR") or ((s.estado or "").upper().strip() != "BORRADOR")

    return render_template(
        "solicitudes_fondos/detalle.html",
        s=s,
        obras_cc=obras_cc,
        secciones=SECCIONES,
        estados=ESTADOS,
        periodos=PERIODOS,
        badge_estado=_badge_class_estado,
        items=items,
        tot=tot,
        total_general=total_general,
        terceros=terceros,
        trabajadores=trabajadores,
        solo_lectura=solo_lectura,
        resumen_anticipos=resumen_anticipos,
    )


# ---------------------------
# Cambiar estado
# ---------------------------
@bp.post("/<int:solicitud_id>/estado")
@role_required("ADMIN", "OPERADOR")
def cambiar_estado(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    estado = (request.form.get("estado") or "").strip().upper()
    if estado not in ESTADOS:
        flash("Estado inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    s.estado = estado
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))


# ---------------------------
# Ítems: agregar / editar / eliminar
# ---------------------------
@bp.post("/<int:solicitud_id>/items/agregar", endpoint="item_agregar")
@role_required("ADMIN", "OPERADOR")
def item_agregar(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    seccion = (request.form.get("seccion") or "").strip().upper()
    if seccion not in dict(SECCIONES):
        flash("Sección inválida.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if seccion == "REMU":
        flash("La sección Remuneraciones se alimenta automáticamente y no admite ítems manuales.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    enforce_registrado = seccion in ("TERC", "VAR")

    tercero_id = request.form.get("tercero_id", type=int)
    trabajador_id = request.form.get("trabajador_id", type=int)

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper() or None
    tipo_documento = (request.form.get("tipo_documento") or "").strip().upper() or None
    nro_doc_num = (request.form.get("nro_documento") or "").strip()
    concepto = (request.form.get("concepto") or "").strip().upper() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    beneficiario_nombre = (request.form.get("beneficiario_nombre") or "").strip() or None
    beneficiario_rut_num = request.form.get("beneficiario_rut_num", type=int)
    beneficiario_dv = (request.form.get("beneficiario_dv") or "").strip().upper() or None
    control_interno = (request.form.get("control_interno") or "").strip() or None

    try:
        monto = _to_decimal_money(request.form.get("monto"))
        if monto < 0:
            raise ValueError
    except Exception:
        flash("Monto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if enforce_registrado:
        if not tercero_id and not trabajador_id:
            flash("Debes seleccionar un Tercero o un Trabajador desde la lista.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        if tercero_id and trabajador_id:
            flash("Selecciona solo un beneficiario: Tercero o Trabajador (no ambos).", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_pago = {"TRANSFERENCIA", "NOMINA_2"}
        if (tipo_pago or "") not in allowed_pago:
            flash("Tipo de pago inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_doc = {"FACTURA", "COMPROBANTE", "GUIA_DESPACHO", "BOLETA_HONORARIOS", "SIN_DOCUMENTO"}
        if (tipo_documento or "") not in allowed_doc:
            flash("Tipo de documento inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_concepto = {
            "CONTRATISTA",
            "SERVICIOS",
            "TRATOS_INTERNOS",
            "PROVEEDORES",
            "PROVISIONES",
            "FINIQUITOS",
            "OTROS",
        }
        if (concepto or "") not in allowed_concepto:
            flash("Concepto inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        nro_documento = f"{tipo_documento}|{nro_doc_num}" if tipo_documento else None

        beneficiario_nombre = None
        beneficiario_rut_num = None
        beneficiario_dv = None
        control_interno = None
    else:
        nro_documento = (request.form.get("nro_documento") or "").strip() or None
        if not tipo_pago:
            tipo_pago = (request.form.get("tipo_pago") or "").strip() or None
        if not concepto:
            concepto = (request.form.get("concepto") or "").strip() or None

    it = SolicitudFondosItem(
        solicitud_id=solicitud_id,
        seccion=seccion,
        tercero_id=tercero_id or None,
        trabajador_id=trabajador_id or None,
        beneficiario_nombre=beneficiario_nombre,
        beneficiario_rut_num=beneficiario_rut_num,
        beneficiario_dv=beneficiario_dv,
        monto=monto,
        tipo_pago=tipo_pago,
        nro_documento=nro_documento,
        concepto=concepto,
        descripcion=descripcion,
        control_interno=control_interno,
        orden=0,
    )
    db.session.add(it)
    db.session.commit()

    flash("Ítem agregado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))


# Alias legacy (templates antiguos): url_for("solicitudes_fondos.agregar_item", ...)
bp.add_url_rule(
    "/<int:solicitud_id>/items/agregar",
    endpoint="agregar_item",
    view_func=item_agregar,
    methods=["POST"],
)


@bp.post("/items/<int:item_id>/editar", endpoint="item_actualizar")
@role_required("ADMIN", "OPERADOR")
def item_actualizar(item_id: int):
    it: SolicitudFondosItem = SolicitudFondosItem.query.get_or_404(item_id)
    s = it.solicitud
    if not s:
        abort(404)

    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    seccion = (it.seccion or "").upper().strip()
    if seccion not in ("TERC", "VAR"):
        flash("Este ítem no admite edición en esta pantalla (solo TERC/VAR).", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    tercero_id = request.form.get("tercero_id", type=int)
    trabajador_id = request.form.get("trabajador_id", type=int)

    if not tercero_id and not trabajador_id:
        flash("Debes seleccionar un Tercero o un Trabajador desde la lista.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    if tercero_id and trabajador_id:
        flash("Selecciona solo un beneficiario: Tercero o Trabajador (no ambos).", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper() or None
    tipo_documento = (request.form.get("tipo_documento") or "").strip().upper() or None
    nro_doc_num = (request.form.get("nro_documento") or "").strip()
    concepto = (request.form.get("concepto") or "").strip().upper() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    allowed_pago = {"TRANSFERENCIA", "NOMINA_2"}
    if (tipo_pago or "") not in allowed_pago:
        flash("Tipo de pago inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    allowed_doc = {"FACTURA", "COMPROBANTE", "GUIA_DESPACHO", "BOLETA_HONORARIOS", "SIN_DOCUMENTO"}
    if (tipo_documento or "") not in allowed_doc:
        flash("Tipo de documento inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    allowed_concepto = {
        "CONTRATISTA",
        "SERVICIOS",
        "TRATOS_INTERNOS",
        "PROVEEDORES",
        "PROVISIONES",
        "FINIQUITOS",
        "OTROS",
    }
    if (concepto or "") not in allowed_concepto:
        flash("Concepto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    try:
        monto = _to_decimal_money(request.form.get("monto"))
        if monto < 0:
            raise ValueError
    except Exception:
        flash("Monto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    nro_documento = f"{tipo_documento}|{nro_doc_num}" if tipo_documento else None

    it.tercero_id = tercero_id or None
    it.trabajador_id = trabajador_id or None

    it.monto = monto
    it.tipo_pago = tipo_pago
    it.nro_documento = nro_documento
    it.concepto = concepto
    it.descripcion = descripcion

    it.beneficiario_nombre = None
    it.beneficiario_rut_num = None
    it.beneficiario_dv = None
    it.control_interno = None

    db.session.commit()
    flash("Ítem actualizado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))


@bp.post("/items/<int:item_id>/eliminar", endpoint="item_eliminar")
@role_required("ADMIN", "OPERADOR")
def item_eliminar(item_id: int):
    it: SolicitudFondosItem = SolicitudFondosItem.query.get_or_404(item_id)
    s = it.solicitud
    if not s:
        abort(404)

    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    if (it.seccion or "").upper().strip() == "REMU":
        flash("La sección Remuneraciones se alimenta automáticamente y no admite eliminación manual.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    db.session.delete(it)
    db.session.commit()
    flash("Ítem eliminado.", "info")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))


@bp.post("/<int:solicitud_id>/items/<int:item_id>/eliminar", endpoint="eliminar_item")
@role_required("ADMIN", "OPERADOR")
def eliminar_item_legacy(solicitud_id: int, item_id: int):
    return item_eliminar(item_id)


@bp.get("/<int:solicitud_id>/editar")
@role_required("ADMIN", "OPERADOR")
def editar(solicitud_id: int):
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))