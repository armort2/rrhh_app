# web/app/blueprints/contratos/routes.py

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ...auth.decorators import role_required
from ...config import generar_nombre_documento
from ...extensions import db
from ...models import (
    Cargo,
    Contrato,
    DocumentoLaboral,
    Empleador,
    EventoLaboral,
    Horario,
    Inasistencia,
    Obra,
    Trabajador,
    Desvinculacion,
)
from ...services.docx_engine import build_contract_docx
from ...services.paths_nextcloud import get_nc_paths
from ...services.pdf_convert import convert_docx_to_pdf
from ...services.storage_nextcloud_fs import ensure_dir
from ...utils import fecha_larga_es, parse_date, parse_decimal, parse_int
from . import bp


# ==========================
# Helpers: RUT formatting
# ==========================

_RUT_CLEAN_RE = re.compile(r"[^0-9kK]")


def split_empleador_rut(raw: str) -> tuple[str, str]:
    """
    Normaliza un RUT desde string libre (con puntos/guión o sin ellos).
    Retorna (rut_digits, dv_upper). Si no es posible, devuelve ("","").
    """
    if not raw:
        return "", ""
    cleaned = _RUT_CLEAN_RE.sub("", str(raw)).upper()
    if len(cleaned) < 2:
        return "", ""
    dv = cleaned[-1]
    rut_digits = re.sub(r"\D", "", cleaned[:-1])
    return rut_digits, dv


def format_rut(rut_digits: str, dv: str) -> str:
    """
    Formatea RUT digits + dv => 12.345.678-9
    Si faltan datos, retorna ''.
    """
    if not rut_digits or not dv:
        return ""
    digits = re.sub(r"\D", "", str(rut_digits))
    if not digits:
        return ""
    dv = str(dv).strip().upper()
    rev = digits[::-1]
    chunks = [rev[i : i + 3] for i in range(0, len(rev), 3)]
    with_dots = ".".join(c[::-1] for c in chunks[::-1])
    return f"{with_dots}-{dv}"


def format_rut_raw(raw: str) -> str:
    """
    Formatea un RUT almacenado como string libre (por ejemplo empleador.rut).
    """
    rut_digits, dv = split_empleador_rut(raw)
    return format_rut(rut_digits, dv)


# ==========================
# Helpers: Control acceso por obra (querys)
# ==========================

def obras_visibles_query():
    """
    Obras visibles para el usuario actual:
    - ADMIN: todas las activas
    - Otros: solo las activas asignadas al usuario (User.obras)
    """
    q = Obra.query.filter(Obra.estado == "ACTIVA")
    if current_user.has_role("ADMIN"):
        return q

    # Fail-closed: si no tiene obras asignadas, no ve nada
    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return q.filter(db.text("1=0"))

    return q.filter(Obra.id.in_(obra_ids))


def aplicar_filtro_obras_autorizadas_a_contratos(query):
    """
    Aplica filtro de obras autorizadas sobre un query de Contrato.
    ADMIN: sin filtro.
    """
    if current_user.has_role("ADMIN"):
        return query

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        # fail-closed: no retorna contratos
        return query.filter(db.text("1=0"))

    return query.filter(Contrato.obra_id.in_(obra_ids))


def assert_contrato_accessible_or_403(contrato: Contrato) -> None:
    """
    Garantiza que el usuario actual pueda acceder al contrato (por obra).
    ADMIN: ok.
    Otros: solo si can_access_obra(contrato.obra_id) es True.
    """
    if current_user.has_role("ADMIN"):
        return
    if not current_user.can_access_obra(getattr(contrato, "obra_id", None)):
        abort(403)


# ==========================
# Dependencias del Contrato
# ==========================

def contrato_dependencias(contrato_id: int) -> dict[str, int]:
    """
    Retorna un dict con conteos de registros relacionados a un contrato.
    Si alguno es > 0, NO debería permitir eliminar.
    """
    c = Contrato.query.get_or_404(contrato_id)

    anexos_ext = c.anexos_extension.count() if hasattr(c, "anexos_extension") else 0
    anexos_ind = c.anexos_indefinido.count() if hasattr(c, "anexos_indefinido") else 0

    desvinc = (
        db.session.query(func.count(Desvinculacion.id))
        .filter(Desvinculacion.contrato_id == c.id)
        .scalar()
        or 0
    )

    eventos = (
        db.session.query(func.count(EventoLaboral.id))
        .filter(EventoLaboral.contrato_id == c.id)
        .scalar()
        or 0
    )

    docs = (
        db.session.query(func.count(DocumentoLaboral.id))
        .filter(DocumentoLaboral.contrato_id == c.id)
        .scalar()
        or 0
    )

    inasistencias = (
        db.session.query(func.count(Inasistencia.id))
        .filter(Inasistencia.contrato_id == c.id)
        .scalar()
        or 0
    )

    return {
        "anexos_extension": int(anexos_ext),
        "anexos_indefinido": int(anexos_ind),
        "desvinculaciones": int(desvinc),
        "eventos": int(eventos),
        "documentos": int(docs),
        "inasistencias": int(inasistencias),
    }


# ==========================
# LISTA
# ==========================

@bp.route("/")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def lista_contratos():
    empleador_ids = request.args.getlist("empleador_id", type=int)
    obra_ids = request.args.getlist("obra_id", type=int)

    estado = (request.args.get("estado", type=str) or "").strip() or None

    inicio_desde_raw = (request.args.get("inicio_desde") or "").strip()
    inicio_hasta_raw = (request.args.get("inicio_hasta") or "").strip()
    inicio_desde = parse_date(inicio_desde_raw) if inicio_desde_raw else None
    inicio_hasta = parse_date(inicio_hasta_raw) if inicio_hasta_raw else None

    query = (
        Contrato.query
        .join(Trabajador)
        .join(Obra)
        .outerjoin(Empleador)
    )

    # ✅ Filtro por obras autorizadas (OPERADOR/REVISOR)
    query = aplicar_filtro_obras_autorizadas_a_contratos(query)

    if empleador_ids:
        query = query.filter(Contrato.empleador_id.in_(empleador_ids))

    # Si el usuario no es ADMIN, además debemos evitar que filtre por obra fuera de su alcance.
    if obra_ids:
        if not current_user.has_role("ADMIN"):
            obra_ids = [oid for oid in obra_ids if current_user.can_access_obra(oid)]
        query = query.filter(Contrato.obra_id.in_(obra_ids))

    if estado:
        query = query.filter(Contrato.estado_contrato == estado)

    if inicio_desde and inicio_hasta:
        query = query.filter(Contrato.fecha_inicio >= inicio_desde, Contrato.fecha_inicio <= inicio_hasta)
    elif inicio_desde:
        query = query.filter(Contrato.fecha_inicio >= inicio_desde)
    elif inicio_hasta:
        query = query.filter(Contrato.fecha_inicio <= inicio_hasta)

    contratos = (
        query.order_by(
            Obra.nombre,
            Trabajador.ap_paterno,
            Trabajador.ap_materno,
            Contrato.fecha_inicio.desc(),
        )
        .all()
    )

    empleadores = Empleador.query.order_by(Empleador.razon_social).all()

    # ✅ Obras para el filtro: ADMIN todas, otros solo asignadas
    obras = obras_visibles_query().order_by(Obra.nombre).all()

    return render_template(
        "contratos/contratos.html",
        contratos=contratos,
        empleadores=empleadores,
        obras=obras,
        filtro_empleador_ids=empleador_ids,
        filtro_obra_ids=obra_ids,
        filtro_estado=estado,
        filtro_inicio_desde=inicio_desde_raw,
        filtro_inicio_hasta=inicio_hasta_raw,
    )


# ==========================
# NUEVO
# ==========================

@bp.route("/nuevo", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def nuevo_contrato():
    next_url = request.args.get("next") or request.form.get("next")

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
            if next_url:
                return redirect(url_for("contratos.nuevo_contrato", next=next_url))
            return redirect(url_for("contratos.nuevo_contrato"))

        empleador_id = parse_int(request.form.get("empleador_id"))
        obra_id = parse_int(request.form.get("obra_id"))
        cargo_id = parse_int(request.form.get("cargo_id"))

        tipo_contrato = (request.form.get("tipo_contrato") or "").strip() or None
        fecha_inicio = parse_date(request.form.get("fecha_inicio"))
        fecha_termino = parse_date(request.form.get("fecha_termino"))

        horario_id = parse_int(request.form.get("horario_id"))
        jornada = (request.form.get("jornada") or "").strip() or None

        horas_semanales = parse_int(request.form.get("horas_semanales"))
        if not horas_semanales and tipo_contrato:
            horas_semanales = 18 if tipo_contrato == "PART_TIME" else 44

        sueldo_base = parse_decimal(request.form.get("sueldo_base"))
        asignacion_movilizacion = parse_decimal(request.form.get("asignacion_movilizacion"))
        asignacion_colacion = parse_decimal(request.form.get("asignacion_colacion"))
        asignacion_herramientas = parse_decimal(request.form.get("asignacion_herramientas"))

        estado_contrato = request.form.get("estado_contrato") or "VIGENTE"

        def _redir_nuevo():
            if next_url:
                return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id, next=next_url))
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id))

        # ✅ Seguridad: OPERADOR solo puede crear contratos en obras asignadas
        if not current_user.has_role("ADMIN"):
            if not obra_id or not current_user.can_access_obra(int(obra_id)):
                abort(403)

        if not empleador_id:
            flash("Debes seleccionar un empleador para el contrato.", "error")
            return _redir_nuevo()

        if not obra_id:
            flash("Debes seleccionar una obra para el contrato.", "error")
            return _redir_nuevo()

        if not cargo_id:
            flash("Debes seleccionar un cargo para este contrato.", "error")
            return _redir_nuevo()

        if not tipo_contrato:
            flash("Debes indicar el tipo de contrato.", "error")
            return _redir_nuevo()

        if not fecha_inicio:
            flash("Debes indicar la fecha de inicio del contrato.", "error")
            return _redir_nuevo()

        if horario_id:
            horario_obj = Horario.query.get(horario_id)
            if not horario_obj:
                flash("El horario seleccionado no existe.", "error")
                return _redir_nuevo()
            if not horario_obj.activo:
                flash("El horario seleccionado no está activo.", "error")
                return _redir_nuevo()

        if estado_contrato == "VIGENTE":
            contrato_vigente = (
                Contrato.query.filter(
                    Contrato.trabajador_id == trabajador.id,
                    Contrato.empleador_id == empleador_id,
                    Contrato.estado_contrato == "VIGENTE",
                ).first()
            )
            if contrato_vigente:
                flash(
                    "Este trabajador ya tiene un contrato VIGENTE con el empleador seleccionado. "
                    "Primero debes terminar ese contrato antes de crear uno nuevo.",
                    "error",
                )
                if next_url:
                    return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id, next=next_url))
                return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

        contrato = Contrato(
            trabajador_id=trabajador.id,
            empleador_id=empleador_id,
            obra_id=obra_id,
            cargo_id=cargo_id,
            tipo_contrato=tipo_contrato,
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,
            horario_id=horario_id or None,
            jornada=jornada,
            horas_semanales=horas_semanales,
            sueldo_base=sueldo_base,
            asignacion_movilizacion=asignacion_movilizacion,
            asignacion_colacion=asignacion_colacion,
            asignacion_herramientas=asignacion_herramientas,
            estado_contrato=estado_contrato,
        )

        db.session.add(contrato)

        if estado_contrato == "VIGENTE":
            if trabajador.obra_id != obra_id:
                trabajador.obra_id = obra_id
            if trabajador.cargo_id != cargo_id:
                trabajador.cargo_id = cargo_id

        db.session.commit()
        flash("Contrato guardado correctamente.", "success")

        if next_url:
            return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id, next=next_url))
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    # GET
    empleadores = Empleador.query.order_by(Empleador.razon_social).all()

    # ✅ Obras visibles según usuario
    obras = obras_visibles_query().order_by(Obra.nombre).all()

    cargos = Cargo.query.order_by(Cargo.nombre).all()
    horarios = Horario.query.filter_by(activo=True).order_by(Horario.nombre).all()

    empleador_default_id = None
    obra_default_id = None
    cargo_default_id = None

    if trabajador:
        # Ojo: si el trabajador tiene obra asignada pero el usuario no tiene acceso, no la preseleccionamos.
        if trabajador.obra and current_user.can_access_obra(trabajador.obra.id):
            obra_default_id = trabajador.obra.id
            if trabajador.obra.empleador_id:
                empleador_default_id = trabajador.obra.empleador_id
        if trabajador.cargo_id:
            cargo_default_id = trabajador.cargo_id

    return render_template(
        "contratos/nuevo_contrato.html",
        trabajador=trabajador,
        empleadores=empleadores,
        obras=obras,
        cargos=cargos,
        horarios=horarios,
        empleador_default_id=empleador_default_id,
        obra_default_id=obra_default_id,
        cargo_default_id=cargo_default_id,
        next_url=next_url,
    )


# ==========================
# EDITAR
# ==========================

@bp.route("/<int:contrato_id>/editar", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def editar_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    assert_contrato_accessible_or_403(contrato)

    trabajador = contrato.trabajador
    next_url = request.args.get("next") or request.form.get("next")

    if request.method == "POST":
        empleador_id = parse_int(request.form.get("empleador_id"))
        obra_id = parse_int(request.form.get("obra_id"))
        cargo_id = parse_int(request.form.get("cargo_id"))

        tipo_contrato = (request.form.get("tipo_contrato") or "").strip() or None
        fecha_inicio = parse_date(request.form.get("fecha_inicio"))
        fecha_termino = parse_date(request.form.get("fecha_termino"))

        horario_id = parse_int(request.form.get("horario_id"))
        jornada = (request.form.get("jornada") or "").strip() or None

        horas_semanales = parse_int(request.form.get("horas_semanales"))
        if not horas_semanales and tipo_contrato:
            horas_semanales = 18 if tipo_contrato == "PART_TIME" else 44

        sueldo_base = parse_decimal(request.form.get("sueldo_base"))
        asignacion_movilizacion = parse_decimal(request.form.get("asignacion_movilizacion"))
        asignacion_colacion = parse_decimal(request.form.get("asignacion_colacion"))
        asignacion_herramientas = parse_decimal(request.form.get("asignacion_herramientas"))

        estado_contrato = request.form.get("estado_contrato") or "VIGENTE"

        def _redir_editar():
            if next_url:
                return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id, next=next_url))
            return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))

        # ✅ Seguridad: OPERADOR solo puede setear obra asignada
        if not current_user.has_role("ADMIN"):
            if not obra_id or not current_user.can_access_obra(int(obra_id)):
                abort(403)

        if not empleador_id:
            flash("Debes seleccionar un empleador para el contrato.", "error")
            return _redir_editar()

        if not obra_id:
            flash("Debes seleccionar una obra para el contrato.", "error")
            return _redir_editar()

        if not cargo_id:
            flash("Debes seleccionar un cargo para este contrato.", "error")
            return _redir_editar()

        if not tipo_contrato:
            flash("Debes indicar el tipo de contrato.", "error")
            return _redir_editar()

        if not fecha_inicio:
            flash("Debes indicar la fecha de inicio del contrato.", "error")
            return _redir_editar()

        if horario_id:
            horario_obj = Horario.query.get(horario_id)
            if not horario_obj:
                flash("El horario seleccionado no existe.", "error")
                return _redir_editar()

            if (not horario_obj.activo) and (contrato.horario_id != horario_obj.id):
                flash("El horario seleccionado no está activo.", "error")
                return _redir_editar()

        if estado_contrato == "VIGENTE":
            otro_vigente = (
                Contrato.query.filter(
                    Contrato.trabajador_id == trabajador.id,
                    Contrato.empleador_id == empleador_id,
                    Contrato.estado_contrato == "VIGENTE",
                    Contrato.id != contrato.id,
                ).first()
            )
            if otro_vigente:
                flash(
                    "Este trabajador ya tiene otro contrato VIGENTE con el empleador seleccionado. "
                    "Primero debes terminar ese contrato antes de dejar este como vigente.",
                    "error",
                )
                return _redir_editar()

        contrato.empleador_id = empleador_id
        contrato.obra_id = obra_id
        contrato.cargo_id = cargo_id

        contrato.tipo_contrato = tipo_contrato
        contrato.fecha_inicio = fecha_inicio
        contrato.fecha_termino = fecha_termino

        contrato.horario_id = horario_id or None
        contrato.jornada = jornada
        contrato.horas_semanales = horas_semanales

        contrato.sueldo_base = sueldo_base
        contrato.asignacion_movilizacion = asignacion_movilizacion
        contrato.asignacion_colacion = asignacion_colacion
        contrato.asignacion_herramientas = asignacion_herramientas

        contrato.estado_contrato = estado_contrato

        if estado_contrato == "VIGENTE":
            if trabajador.obra_id != obra_id:
                trabajador.obra_id = obra_id
            if trabajador.cargo_id != cargo_id:
                trabajador.cargo_id = cargo_id

        db.session.commit()
        flash("Contrato actualizado correctamente.", "success")

        if next_url:
            return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id, next=next_url))
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    empleadores = Empleador.query.order_by(Empleador.razon_social).all()
    obras = obras_visibles_query().order_by(Obra.nombre).all()
    cargos = Cargo.query.order_by(Cargo.nombre).all()

    horarios_activos = Horario.query.filter_by(activo=True).order_by(Horario.nombre).all()
    horarios = horarios_activos
    if contrato.horario_id:
        h_actual = Horario.query.get(contrato.horario_id)
        if h_actual and (not h_actual.activo):
            horarios = [h_actual] + horarios_activos

    rut_trabajador_formateado = format_rut(getattr(trabajador, "rut", "") or "", getattr(trabajador, "dv", "") or "")

    deps = contrato_dependencias(contrato.id)
    puede_eliminar = all(v == 0 for v in deps.values())

    return render_template(
        "contratos/contrato_editar.html",
        contrato=contrato,
        trabajador=trabajador,
        empleadores=empleadores,
        obras=obras,
        cargos=cargos,
        horarios=horarios,
        next_url=next_url,
        rut_trabajador_formateado=rut_trabajador_formateado,
        deps=deps,
        puede_eliminar=puede_eliminar,
    )


# ==========================
# DETALLE
# ==========================

@bp.route("/<int:contrato_id>")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def contrato_detalle(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    assert_contrato_accessible_or_403(contrato)

    trabajador = contrato.trabajador
    rut_trabajador_formateado = format_rut(trabajador.rut or "", trabajador.dv or "")
    return render_template(
        "contratos/contrato_detalle.html",
        contrato=contrato,
        rut_trabajador_formateado=rut_trabajador_formateado,
    )


# ===========================
# ELIMINAR
# ===========================

@bp.route("/<int:contrato_id>/eliminar", methods=["POST"])
@role_required("ADMIN", "OPERADOR")
def eliminar_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    assert_contrato_accessible_or_403(contrato)

    trabajador = contrato.trabajador
    next_url = request.args.get("next") or request.form.get("next")

    deps = contrato_dependencias(contrato.id)
    total_deps = sum(deps.values())

    if total_deps > 0:
        flash(
            "No se puede eliminar el contrato porque tiene registros asociados. "
            "Primero elimina/anula esos registros relacionados, o marca el contrato como TERMINADO.",
            "error",
        )
        return redirect(
            url_for("contratos.editar_contrato", contrato_id=contrato.id, next=next_url)
            if next_url
            else url_for("contratos.editar_contrato", contrato_id=contrato.id)
        )

    contrato_fue_vigente = (contrato.estado_contrato == "VIGENTE")
    trabajador_id = getattr(trabajador, "id", None)

    try:
        db.session.delete(contrato)
        db.session.flush()

        if contrato_fue_vigente and trabajador_id:
            otro_vigente = (
                Contrato.query.filter(
                    Contrato.trabajador_id == trabajador_id,
                    Contrato.estado_contrato == "VIGENTE",
                )
                .order_by(Contrato.fecha_inicio.desc())
                .first()
            )

            if otro_vigente:
                if trabajador.obra_id != otro_vigente.obra_id:
                    trabajador.obra_id = otro_vigente.obra_id
                if trabajador.cargo_id != otro_vigente.cargo_id:
                    trabajador.cargo_id = otro_vigente.cargo_id
            else:
                flash(
                    "Contrato eliminado. Atención: era un contrato VIGENTE y no existe otro vigente para re-sincronizar "
                    "automáticamente la ficha del trabajador. Revisa Obra/Cargo en la ficha.",
                    "warning",
                )

        db.session.commit()
        flash("Contrato eliminado correctamente.", "success")

    except IntegrityError:
        db.session.rollback()
        flash(
            "No se pudo eliminar el contrato por restricción de integridad (FK). "
            "Esto normalmente indica registros relacionados. Revisa anexos/eventos/documentos/asistencias.",
            "error",
        )
        return redirect(
            url_for("contratos.editar_contrato", contrato_id=contrato.id, next=next_url)
            if next_url
            else url_for("contratos.editar_contrato", contrato_id=contrato.id)
        )

    except Exception as e:
        db.session.rollback()
        flash(f"No se pudo eliminar el contrato: {e}", "error")
        return redirect(
            url_for("contratos.editar_contrato", contrato_id=contrato.id, next=next_url)
            if next_url
            else url_for("contratos.editar_contrato", contrato_id=contrato.id)
        )

    if trabajador_id:
        if next_url:
            return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador_id, next=next_url))
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador_id))

    return redirect(url_for("contratos.lista_contratos"))


# ==========================
# GENERAR (DOCX/PDF) + Nextcloud
# ==========================

@bp.route("/<int:contrato_id>/generar", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def generar_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    assert_contrato_accessible_or_403(contrato)

    if request.method == "GET":
        return render_template("contratos/contrato_generar.html", contrato=contrato)

    formato = (request.form.get("formato") or "DOCX").upper()
    if formato not in ("DOCX", "PDF", "AMBOS"):
        formato = "DOCX"

    if not contrato.trabajador:
        flash("Contrato sin trabajador asociado.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    if not contrato.empleador:
        flash("El contrato no tiene empleador asignado. No se puede determinar carpeta de destino.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    if not contrato.cargo_id:
        flash("El contrato no tiene cargo asociado. No se puede generar.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    if not getattr(contrato, "obra", None):
        flash("El contrato no tiene obra asignada. No se puede determinar centro de costo.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    centro_costo = (getattr(contrato.obra, "centro_costo", "") or "").strip()
    if not centro_costo:
        flash(f"La obra '{getattr(contrato.obra, 'nombre', 'SIN_NOMBRE')}' no tiene centro de costo definido.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    next_url = request.args.get("next") or request.form.get("next")

    templates_root = Path(current_app.root_path) / "document_templates" / "contratos"
    base_tpl = templates_root / "contrato_base.docx"
    cargos_tpl = templates_root / "cargos.docx"

    if not base_tpl.exists():
        flash("No se encontró contrato_base.docx en document_templates/contratos.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    if not cargos_tpl.exists():
        flash("No se encontró cargos.docx en document_templates/contratos.", "error")
        return redirect(url_for("contratos.contrato_detalle", contrato_id=contrato.id))

    trabajador = contrato.trabajador
    obra = contrato.obra
    empleador = contrato.empleador

    jornada_texto = (contrato.jornada or "").strip() or None
    if not jornada_texto and contrato.horario and contrato.horario.descripcion:
        jornada_texto = contrato.horario.descripcion.strip() or None

    rut_trabajador_formateado = format_rut(getattr(trabajador, "rut", "") or "", getattr(trabajador, "dv", "") or "")
    rut_empleador_formateado = format_rut_raw(getattr(empleador, "rut", "") or "")

    rep_legal_rut_raw = getattr(empleador, "rut_rep_legal", "") or ""
    rep_legal_rut_formateado = format_rut_raw(rep_legal_rut_raw)

    variables = {
        "{{TRABAJADOR_NOMBRES}}": trabajador.nombres or "",
        "{{TRABAJADOR_AP_PATERNO}}": trabajador.ap_paterno or "",
        "{{TRABAJADOR_AP_MATERNO}}": trabajador.ap_materno or "",
        "{{TRABAJADOR_RUT}}": rut_trabajador_formateado,
        "{{TRABAJADOR_DIRECCION}}": trabajador.direccion or "",
        "{{TRABAJADOR_COMUNA}}": trabajador.comuna or "",
        "{{TRABAJADOR_NACIONALIDAD}}": ((trabajador.nacionalidad or "").strip().lower()),
        "{{TRABAJADOR_TELEFONO}}": trabajador.telefono or "",
        "{{TRABAJADOR_CORREO}}": trabajador.correo or "",
        "{{TRABAJADOR_FECHA_NACIMIENTO}}": fecha_larga_es(trabajador.fecha_nacimiento),
        "{{TRABAJADOR_ESTADO_CIVIL}}": ((trabajador.estado_civil or "").strip().lower()),
        "{{EMPLEADOR_RAZON_SOCIAL}}": empleador.razon_social or "",
        "{{EMPLEADOR_RUT}}": rut_empleador_formateado or (empleador.rut or ""),
        "{{EMPLEADOR_DIRECCION}}": empleador.direccion or "",
        "{{EMPLEADOR_COMUNA}}": empleador.comuna or "",
        "{{REP_LEGAL_RUT}}": rep_legal_rut_formateado or rep_legal_rut_raw,
        "{{REP_LEGAL_NOMBRE}}": (getattr(empleador, "nombre_rep_legal", "") or ""),
        "{{OBRA_NOMBRE}}": obra.nombre if obra else "",
        "{{OBRA_COMUNA}}": obra.comuna if obra else "",
        "{{OBRA_DIRECCION}}": getattr(obra, "direccion", "") if obra else "",
        "{{CONTRATO_FECHA_INGRESO}}": fecha_larga_es(contrato.fecha_inicio),
        "{{CONTRATO_FECHA_TERMINO}}": fecha_larga_es(contrato.fecha_termino),
        "{{CONTRATO_JORNADA}}": jornada_texto or "",
        "{{CONTRATO_HORAS_SEMANALES}}": (str(contrato.horas_semanales) if contrato.horas_semanales else ""),
        "{{HRS_SEMANALES}}": (str(contrato.horas_semanales) if contrato.horas_semanales else ""),
        "{{CARGO_NOMBRE}}": contrato.cargo.nombre if contrato.cargo else "",
        "{{HORARIO_DESCRIPCION}}": (
            contrato.horario.descripcion if contrato.horario and contrato.horario.descripcion else ""
        ),
        "{{CONTRATO_SUELDO_BASE}}": (
            f"{int(contrato.sueldo_base):,}".replace(",", ".") if contrato.sueldo_base else "0"
        ),
        "{{ASIG_MOVILIZACION}}": (
            f"{int(contrato.asignacion_movilizacion):,}".replace(",", ".")
            if contrato.asignacion_movilizacion
            else "0"
        ),
        "{{ASIG_COLACION}}": (
            f"{int(contrato.asignacion_colacion):,}".replace(",", ".") if contrato.asignacion_colacion else "0"
        ),
        "{{ASIG_HERRAMIENTAS}}": (
            f"{int(contrato.asignacion_herramientas):,}".replace(",", ".")
            if contrato.asignacion_herramientas
            else "0"
        ),
        "{{AFP_NOMBRE}}": trabajador.afp.nombre if trabajador.afp else "",
        "{{SALUD_NOMBRE}}": trabajador.salud.nombre if trabajador.salud else "",
        "{{BANCO_NOMBRE}}": trabajador.banco.nombre if trabajador.banco else "",
        "{{BANCO_NUMERO_CUENTA}}": trabajador.cuenta_numero or "",
    }

    nc = get_nc_paths()
    dest_dir = nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=trabajador.nombres or "",
        ap_paterno=trabajador.ap_paterno or "",
        ap_materno=trabajador.ap_materno or "",
        tipo_doc="CONTRATOS",
    )

    try:
        ensure_dir(dest_dir)

        nombre_docx = generar_nombre_documento(
            tipo=f"CONTRATO_{contrato.tipo_contrato or 'SIN_TIPO'}",
            ap_paterno=trabajador.ap_paterno or "SIN_APELLIDO",
            fecha_ref=contrato.fecha_inicio,
            extension="docx",
        )
        docx_final = dest_dir / nombre_docx

        out_tmp = Path(current_app.instance_path) / "generated_docs"
        ensure_dir(out_tmp)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        docx_tmp = out_tmp / f"tmp_contrato_{contrato.id}_{stamp}.docx"

        build_contract_docx(
            base_template_path=base_tpl,
            cargos_library_path=cargos_tpl,
            cargo_id=contrato.cargo_id,
            variables=variables,
            output_path=docx_tmp,
        )

        docx_final.write_bytes(docx_tmp.read_bytes())

        if formato in ("PDF", "AMBOS"):
            nombre_pdf = generar_nombre_documento(
                tipo=f"CONTRATO_{contrato.tipo_contrato or 'SIN_TIPO'}",
                ap_paterno=trabajador.ap_paterno or "SIN_APELLIDO",
                fecha_ref=contrato.fecha_inicio,
                extension="pdf",
            )
            pdf_final = dest_dir / nombre_pdf

            pdf_tmp_dir = out_tmp / "pdf"
            ensure_dir(pdf_tmp_dir)
            pdf_tmp = convert_docx_to_pdf(docx_tmp, pdf_tmp_dir)

            pdf_final.write_bytes(pdf_tmp.read_bytes())

        if formato == "DOCX":
            flash("Contrato generado y guardado en Nextcloud: DOCX", "success")
        elif formato == "PDF":
            flash("Contrato generado y guardado en Nextcloud: PDF", "success")
        else:
            flash("Contrato generado y guardado en Nextcloud: DOCX + PDF", "success")

    except Exception as e:
        flash(f"No se pudo generar/guardar el contrato: {e}", "error")

    return redirect(
        url_for("contratos.contrato_detalle", contrato_id=contrato.id, next=next_url)
        if next_url
        else url_for("contratos.contrato_detalle", contrato_id=contrato.id)
    )
