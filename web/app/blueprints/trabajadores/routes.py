# web/app/blueprints/trabajadores/routes.py

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import exists, and_, or_, func, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, load_only

from ...extensions import db
from ...models import (
    Trabajador,
    Obra,
    AFP,
    Salud,
    Banco,
    CajaCompensacion,
    Cargo,
    Contrato,
    EventoLaboral,
    AnexoExtensionContrato,
    AnexoIndefinidoContrato,  # ✅ NUEVO
    Empleador,
    Desvinculacion,
    Inasistencia,
)
from ...utils import parse_date, parse_int, parse_decimal

bp = Blueprint("trabajadores", __name__, url_prefix="/trabajadores")


# ===========================
# Helpers
# ===========================

def is_checked(field_name: str) -> bool:
    val = request.form.get(field_name)
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "on", "true", "yes", "y", "si", "sí"}


_RUT_CLEAN_RE = re.compile(r"[^0-9kK]")


def split_rut(raw: str) -> tuple[str, str]:
    if not raw:
        return "", ""

    cleaned = _RUT_CLEAN_RE.sub("", str(raw)).upper()
    if len(cleaned) < 2:
        return "", ""

    dv = cleaned[-1]
    rut_digits = re.sub(r"\D", "", cleaned[:-1])

    if not rut_digits or not dv:
        return "", ""

    if not (dv.isdigit() or dv == "K"):
        return "", ""

    return rut_digits, dv


def _safe_next_url(next_url: str | None) -> str | None:
    if not next_url:
        return None
    u = urlparse(next_url)
    # Permitimos solo rutas internas (sin scheme ni netloc)
    if u.scheme or u.netloc:
        return None
    return next_url


def _allowed_obra_ids_for_user() -> list[int]:
    """
    Devuelve IDs de obras visibles para el usuario actual.
    - ADMIN: [] (significa "todas" / sin scoping)
    - Otros: lista de obras asignadas
    """
    if current_user.has_role("ADMIN"):
        return []
    return [o.id for o in (current_user.obras or [])]


def _enforce_access_to_obra(obra_id: int | None) -> None:
    """
    Bloquea acceso si el usuario no puede ver esa obra (403).
    """
    if current_user.has_role("ADMIN"):
        return
    if obra_id is None or not current_user.can_access_obra(int(obra_id)):
        abort(403)


def format_rut(rut_digits: str, dv: str) -> str:
    if not rut_digits or not dv:
        return ""
    digits = re.sub(r"\D", "", str(rut_digits))
    if not digits:
        return ""
    dv = str(dv).strip().upper()

    rev = digits[::-1]
    chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    with_dots = ".".join(c[::-1] for c in chunks[::-1])
    return f"{with_dots}-{dv}"


def trabajador_rut_formateado(t: Trabajador) -> str:
    rut_digits = getattr(t, "rut", "") or ""
    dv = getattr(t, "dv", "") or ""
    if not dv:
        return str(rut_digits)
    return format_rut(rut_digits, dv)


def normalizar_y_guardar_rut_en_trabajador(t: Trabajador, rut_input: str) -> None:
    rut_digits, dv = split_rut(rut_input)
    if not rut_digits or not dv:
        raise ValueError("RUT inválido. Debe incluir dígito verificador (ej: 12.345.678-9).")

    t.rut = rut_digits
    if hasattr(t, "dv"):
        t.dv = dv


# ===========================
# LISTADO TRABAJADORES
# ===========================

@bp.get("/")
@login_required
def listado_trabajadores():
    allowed_obra_ids = _allowed_obra_ids_for_user()

    # Si no es ADMIN y no tiene obras asignadas, bloqueamos.
    if (not current_user.has_role("ADMIN")) and (not allowed_obra_ids):
        abort(403)

    # Inputs filtros (multiselect)
    filtro_empleador_ids = request.args.getlist("empleador_id", type=int)
    filtro_obra_ids = request.args.getlist("obra_id", type=int)
    filtro_cargo_ids = request.args.getlist("cargo_id", type=int)
    filtro_estado = (request.args.get("estado") or "").strip().upper()  # "" | "VIGENTE" | "NO_VIGENTE"

    # Blindaje: si usuario no-admin intenta filtrar por obra no asignada -> se ignora
    if allowed_obra_ids:
        filtro_obra_ids = [oid for oid in filtro_obra_ids if oid in allowed_obra_ids]

    # ✅ Buscador (nombre/apellidos/RUT)
    q_busqueda = (request.args.get("q") or "").strip()

    # Paginación
    page = request.args.get("page", 1, type=int)
    per_page = 15

    q = Trabajador.query

    # Scoping por obra (no-admin)
    if allowed_obra_ids:
        q = q.filter(Trabajador.obra_id.in_(allowed_obra_ids))

    # Definición "contrato vigente"
    hoy = date.today()
    vigente_predicates = [Contrato.estado_contrato == "VIGENTE"]

    # Respetar rango real si existen fechas
    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        vigente_predicates.append(Contrato.fecha_inicio <= hoy)
        vigente_predicates.append(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))

    contrato_vigente_exists = exists().where(
        and_(
            Contrato.trabajador_id == Trabajador.id,
            *vigente_predicates,
        )
    )

    # Filtro por estado
    if filtro_estado == "VIGENTE":
        q = q.filter(contrato_vigente_exists)
    elif filtro_estado == "NO_VIGENTE":
        q = q.filter(~contrato_vigente_exists)

    # Filtros por FK directas
    if filtro_obra_ids:
        q = q.filter(Trabajador.obra_id.in_(filtro_obra_ids))

    if filtro_cargo_ids:
        q = q.filter(Trabajador.cargo_id.in_(filtro_cargo_ids))

    # Filtro por empleador vía contratos vigentes
    if filtro_empleador_ids:
        contrato_vigente_empleador_exists = exists().where(
            and_(
                Contrato.trabajador_id == Trabajador.id,
                Contrato.empleador_id.in_(filtro_empleador_ids),
                *vigente_predicates,
            )
        )
        q = q.filter(contrato_vigente_empleador_exists)

    # ✅ Aplicar buscador (soporta "Nombre Apellido" por tokens)
    if q_busqueda:
        tokens = [t for t in re.split(r"\s+", q_busqueda.strip()) if t]

        rut_digits, _dv = split_rut(q_busqueda)
        if not rut_digits:
            rut_digits = re.sub(r"\D", "", q_busqueda)

        token_predicates = []
        for tok in tokens:
            like_tok = f"%{tok}%"
            tok_digits = re.sub(r"\D", "", tok)
            rut_like_tok = f"%{tok_digits}%" if tok_digits else None

            ors = [
                func.coalesce(Trabajador.nombres, "").ilike(like_tok),
                func.coalesce(Trabajador.ap_paterno, "").ilike(like_tok),
                func.coalesce(Trabajador.ap_materno, "").ilike(like_tok),
            ]

            if rut_like_tok:
                ors.append(func.cast(Trabajador.rut, String).ilike(rut_like_tok))

            token_predicates.append(or_(*ors))

        if token_predicates:
            q = q.filter(and_(*token_predicates))
        else:
            like = f"%{q_busqueda}%"
            q = q.filter(
                or_(
                    func.coalesce(Trabajador.nombres, "").ilike(like),
                    func.coalesce(Trabajador.ap_paterno, "").ilike(like),
                    func.coalesce(Trabajador.ap_materno, "").ilike(like),
                )
            )

        if rut_digits:
            q = q.filter(func.cast(Trabajador.rut, String).ilike(f"%{rut_digits}%"))

    total = q.count()
    total_pages = (total + per_page - 1) // per_page

    trabajadores = (
        q.order_by(
            func.coalesce(func.btrim(Trabajador.ap_paterno), "").asc(),
            func.coalesce(func.btrim(Trabajador.ap_materno), "").asc(),
            func.coalesce(func.btrim(Trabajador.nombres), "").asc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    ids = [t.id for t in trabajadores]
    vigentes_ids: set[int] = set()

    if ids:
        q_vig = (
            db.session.query(Contrato.trabajador_id)
            .filter(Contrato.trabajador_id.in_(ids))
            .filter(*vigente_predicates)
            .distinct()
            .all()
        )
        vigentes_ids = {row[0] for row in q_vig}

    estado_trabajador_map = {tid: ("VIGENTE" if tid in vigentes_ids else "NO_VIGENTE") for tid in ids}

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    if allowed_obra_ids:
        obras = (
            Obra.query
            .filter(Obra.id.in_(allowed_obra_ids))
            .order_by(Obra.nombre.asc())
            .all()
        )
    else:
        obras = Obra.query.order_by(Obra.nombre.asc()).all()

    cargos = Cargo.query.order_by(Cargo.nombre.asc()).all()

    return render_template(
        "trabajadores/trabajadores_listado.html",
        trabajadores=trabajadores,
        empleadores=empleadores,
        obras=obras,
        cargos=cargos,
        filtro_empleador_ids=filtro_empleador_ids,
        filtro_obra_ids=filtro_obra_ids,
        filtro_cargo_ids=filtro_cargo_ids,
        filtro_estado=filtro_estado,
        estado_trabajador_map=estado_trabajador_map,
        trabajador_rut_formateado=trabajador_rut_formateado,
        page=page,
        total_pages=total_pages,
        q=q_busqueda,
    )


# ===========================
# FICHA (DETALLE) TRABAJADOR
# ===========================

@bp.route("/<int:trabajador_id>", methods=["GET"])
@login_required
def detalle_trabajador(trabajador_id: int):
    trabajador = Trabajador.query.get_or_404(trabajador_id)
    _enforce_access_to_obra(trabajador.obra_id)

    contratos = (
        Contrato.query
        .filter_by(trabajador_id=trabajador.id)
        .order_by(Contrato.id.desc())
        .all()
    )

    hoy = date.today()

    q_vig = (
        Contrato.query
        .filter_by(trabajador_id=trabajador.id, estado_contrato="VIGENTE")
    )

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q_vig = (
            q_vig
            .filter(Contrato.fecha_inicio <= hoy)
            .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    contrato_vigente_actual = (
        q_vig
        .order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc())
        .first()
    )

    contrato_contexto = contrato_vigente_actual or (contratos[0] if contratos else None)

    anexos_contrato_vigente = []
    anexos_indefinidos_contrato_vigente = []

    if contrato_contexto:
        anexos_contrato_vigente = (
            AnexoExtensionContrato.query
            .filter_by(contrato_id=contrato_contexto.id)
            .order_by(
                AnexoExtensionContrato.fecha_anexo.desc(),
                AnexoExtensionContrato.id.desc(),
            )
            .all()
        )

        anexos_indefinidos_contrato_vigente = (
            AnexoIndefinidoContrato.query
            .filter_by(contrato_id=contrato_contexto.id)
            .order_by(
                AnexoIndefinidoContrato.fecha_anexo.desc(),
                AnexoIndefinidoContrato.id.desc(),
            )
            .all()
        )

    eventos = (
        EventoLaboral.query
        .filter_by(trabajador_id=trabajador.id)
        .order_by(EventoLaboral.fecha_evento.desc(), EventoLaboral.id.desc())
        .all()
    )

    desvinculaciones = (
        Desvinculacion.query
        .options(
            load_only(
                Desvinculacion.id,
                Desvinculacion.trabajador_id,
                Desvinculacion.contrato_id,
                Desvinculacion.empleador_id,
                Desvinculacion.obra_id,
                Desvinculacion.causal_id,
                Desvinculacion.fecha_aviso,
                Desvinculacion.fecha_termino,
                Desvinculacion.motivo_detalle,
                Desvinculacion.estado,
                Desvinculacion.carta_nombre,
                Desvinculacion.carta_ruta,
                Desvinculacion.finiquito_nombre,
                Desvinculacion.finiquito_ruta,
                Desvinculacion.creado_en,
                Desvinculacion.actualizado_en,
            ),
            joinedload(Desvinculacion.causal),
        )
        .filter(Desvinculacion.trabajador_id == trabajador.id)
        .order_by(Desvinculacion.id.desc())
        .all()
    )

    rut_formateado = trabajador_rut_formateado(trabajador)

    def _fmt_hhmm(minutos: int | None) -> str:
        if not minutos:
            return ""
        hh = minutos // 60
        mm = minutos % 60
        return f"{hh:02d}:{mm:02d}"

    desde_30 = hoy - timedelta(days=30)
    inasistencias_ultimas = (
        Inasistencia.query
        .filter(Inasistencia.trabajador_id == trabajador.id)
        .filter(Inasistencia.fecha >= desde_30)
        .order_by(Inasistencia.fecha.desc(), Inasistencia.id.desc())
        .limit(50)
        .all()
    )

    mes_actual = hoy.strftime("%Y-%m")

    def _fmt_fecha(d):
        try:
            return d.strftime("%d-%m-%Y") if d else "-"
        except Exception:
            return "-"

    def _url_ext_ver_todos(contrato_id: int) -> str:
        return url_for("anexos.anexos_listado", contrato_id=contrato_id)

    def _url_ext_detalle(anexo_id: int) -> str:
        return url_for("anexos.anexo_extension_detalle", anexo_id=anexo_id)

    def _url_ind_ver_todos(contrato_id: int) -> str:
        return url_for("anexos_indefinidos.listado_por_contrato", contrato_id=contrato_id)

    def _url_ind_detalle(anexo_id: int) -> str:
        return url_for("anexos_indefinidos.detalle", anexo_id=anexo_id)

    documentos_grupos = []

    if contrato_contexto:
        documentos_grupos.append({
            "key": "anexos_extension",
            "titulo": "Anexos de extensión de contrato",
            "subtitulo": "Prórrogas / renovaciones (típicamente plazo fijo).",
            "ver_todos_url": _url_ext_ver_todos(contrato_contexto.id),
            "items": [
                {
                    "id": a.id,
                    "titulo": f"Anexo extensión #{a.id}",
                    "fecha": _fmt_fecha(getattr(a, "fecha_anexo", None)),
                    "estado": (getattr(a, "estado", None) or "").upper() or None,
                    "ver_url": _url_ext_detalle(a.id),
                    "editar_url": url_for("anexos.anexo_extension_editar", anexo_id=a.id),
                    "generar_url": url_for("anexos.anexo_extension_generar", anexo_id=a.id),
                    "docx_ruta": getattr(a, "docx_ruta", None),
                    "pdf_ruta": getattr(a, "pdf_ruta", None),
                }
                for a in (anexos_contrato_vigente or [])
            ],
        })

        documentos_grupos.append({
            "key": "anexos_indefinidos",
            "titulo": "Anexos de cambio a indefinido",
            "subtitulo": "Formalización de paso a contrato indefinido.",
            "ver_todos_url": _url_ind_ver_todos(contrato_contexto.id),
            "items": [
                {
                    "id": a.id,
                    "titulo": f"Anexo indefinido #{a.id}",
                    "fecha": _fmt_fecha(getattr(a, "fecha_anexo", None)),
                    "estado": (getattr(a, "estado", None) or "").upper() or None,
                    "ver_url": _url_ind_detalle(a.id),
                    "editar_url": url_for("anexos_indefinidos.editar", anexo_id=a.id),
                    "generar_url": url_for("anexos_indefinidos.generar", anexo_id=a.id),
                    "docx_ruta": getattr(a, "docx_ruta", None),
                    "pdf_ruta": getattr(a, "pdf_ruta", None),
                }
                for a in (anexos_indefinidos_contrato_vigente or [])
            ],
        })

        documentos_grupos.extend([
            {
                "key": "anexos_remuneraciones",
                "titulo": "Anexos de remuneraciones",
                "subtitulo": "Cambios de sueldo, bonos, asignaciones, etc.",
                "ver_todos_url": None,
                "items": [],
            },
            {
                "key": "egresos_acuerdos_pago",
                "titulo": "Egresos y acuerdos de pago",
                "subtitulo": "Egresos, acuerdos de pago y regularizaciones asociadas al contrato.",
                "ver_todos_url": None,
                "items": [],
            },
            {
                "key": "amonestaciones",
                "titulo": "Amonestaciones",
                "subtitulo": "Amonestaciones y medidas disciplinarias.",
                "ver_todos_url": None,
                "items": [],
            },
            {
                "key": "desvinculaciones",
                "titulo": "Desvinculaciones",
                "subtitulo": "Cartas de aviso y finiquitos asociados al contrato.",
                "ver_todos_url": url_for("desvinculaciones.listado"),
                "items": [
                    {
                        "id": d.id,
                        "titulo": f"Desvinculación #{d.id} — {d.causal.causal_resumida if d.causal else 'Causal'}",
                        "fecha": _fmt_fecha(getattr(d, "fecha_termino", None)),
                        "estado": (getattr(d, "estado", None) or "").upper() or None,
                        "ver_url": url_for("desvinculaciones.detalle", desvinculacion_id=d.id),
                        "editar_url": None,
                        "generar_url": None,
                        "docx_ruta": getattr(d, "carta_ruta", None),
                        "pdf_ruta": getattr(d, "finiquito_ruta", None),
                    }
                    for d in (desvinculaciones or [])
                ],
            },
        ])

    acciones_documentos = []
    if contrato_contexto:
        acciones_documentos = [
            {
                "label": "➕ Generar anexo extensión",
                "class": "btn btn-primary",
                "url": url_for("anexos.anexo_extension", contrato_id=contrato_contexto.id),
                "hint": None,
            },
            {
                "label": "📌 Generar anexo indefinido",
                "class": "btn btn-outline-primary",
                "url": url_for("anexos_indefinidos.nuevo", contrato_id=contrato_contexto.id),
                "hint": None,
            },
            {
                "label": "➕ Crear nuevo contrato",
                "class": "btn btn-outline-secondary",
                "url": url_for("contratos.nuevo_contrato", trabajador_id=trabajador.id),
                "hint": None,
            },
            {
                "label": "➕ Iniciar desvinculación",
                "class": "btn btn-danger",
                "url": url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id),
                "hint": "Crea borrador y luego emite.",
            },
        ]

    return render_template(
        "trabajadores/trabajador_detalle.html",
        trabajador=trabajador,
        contratos=contratos,
        contrato_vigente_actual=contrato_vigente_actual,
        contrato_contexto=contrato_contexto,
        anexos_contrato_vigente=anexos_contrato_vigente,
        anexos_indefinidos_contrato_vigente=anexos_indefinidos_contrato_vigente,
        documentos_grupos=documentos_grupos,
        acciones_documentos=acciones_documentos,
        eventos=eventos,
        rut_formateado=rut_formateado,
        inasistencias_ultimas=inasistencias_ultimas,
        inasistencias_fmt_hhmm=_fmt_hhmm,
        mes_actual=mes_actual,
    )


# ===========================
# EDITAR TRABAJADOR
# ===========================

@bp.route("/<int:trabajador_id>/editar", methods=["GET", "POST"])
@login_required
def editar_trabajador(trabajador_id):
    trabajador = Trabajador.query.get_or_404(trabajador_id)
    _enforce_access_to_obra(trabajador.obra_id)

    if request.method == "POST":
        rut_input = request.form.get("rut")
        nombres = request.form.get("nombres")
        ap_paterno = request.form.get("ap_paterno")

        ap_materno = (request.form.get("ap_materno") or "").strip() or None

        obra_id = parse_int(request.form.get("obra_id"))
        _enforce_access_to_obra(obra_id)

        cargo_id = parse_int(request.form.get("cargo_id"))

        if not obra_id:
            flash("Debes seleccionar una obra.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        if not cargo_id:
            flash("Debes seleccionar un cargo.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        if not (rut_input and nombres and ap_paterno):
            flash("Completa RUT, nombres y apellido paterno.", "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        try:
            normalizar_y_guardar_rut_en_trabajador(trabajador, rut_input)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("trabajadores.editar_trabajador", trabajador_id=trabajador.id))

        fecha_nacimiento = parse_date(request.form.get("fecha_nacimiento"))
        nacionalidad = request.form.get("nacionalidad") or None
        sexo = request.form.get("sexo") or None
        estado_civil = request.form.get("estado_civil") or None

        direccion = request.form.get("direccion") or None
        comuna = request.form.get("comuna") or None
        telefono = request.form.get("telefono") or None
        telefono_emergencia = request.form.get("telefono_emergencia") or None
        correo = request.form.get("correo") or None

        banking_fields_present = (
            ("banco_id" in request.form)
            or ("tipo_cuenta" in request.form)
            or ("cuenta_numero" in request.form)
        )

        if banking_fields_present:
            banco_id = parse_int(request.form.get("banco_id"))
            tipo_cuenta = request.form.get("tipo_cuenta") or None
            cuenta_numero = request.form.get("cuenta_numero") or None

            cuenta_rut = None
            if tipo_cuenta == "CTA_RUT":
                cuenta_numero = trabajador.rut or None
                cuenta_rut = trabajador.rut or None
            else:
                cuenta_numero = cuenta_numero or None

            trabajador.banco_id = banco_id
            trabajador.tipo_cuenta = tipo_cuenta
            trabajador.cuenta_rut = cuenta_rut
            trabajador.cuenta_numero = cuenta_numero

        pago_fields_present = (
            ("pago_tercero_activo" in request.form)
            or ("pago_tercero_rut" in request.form)
            or ("pago_tercero_nombre" in request.form)
            or ("pago_tercero_banco_id" in request.form)
            or ("pago_tercero_tipo_cuenta" in request.form)
            or ("pago_tercero_cuenta_numero" in request.form)
        )

        if pago_fields_present:
            pago_tercero_activo = is_checked("pago_tercero_activo")
            pago_tercero_rut = request.form.get("pago_tercero_rut") or None
            pago_tercero_nombre = request.form.get("pago_tercero_nombre") or None
            pago_tercero_banco_id = parse_int(request.form.get("pago_tercero_banco_id"))
            pago_tercero_tipo_cuenta = request.form.get("pago_tercero_tipo_cuenta") or None
            pago_tercero_cuenta_numero = request.form.get("pago_tercero_cuenta_numero") or None

            if not pago_tercero_activo:
                pago_tercero_rut = None
                pago_tercero_nombre = None
                pago_tercero_banco_id = None
                pago_tercero_tipo_cuenta = None
                pago_tercero_cuenta_numero = None

            trabajador.pago_tercero_activo = pago_tercero_activo
            trabajador.pago_tercero_rut = pago_tercero_rut
            trabajador.pago_tercero_nombre = pago_tercero_nombre
            trabajador.pago_tercero_banco_id = pago_tercero_banco_id
            trabajador.pago_tercero_tipo_cuenta = pago_tercero_tipo_cuenta
            trabajador.pago_tercero_cuenta_numero = pago_tercero_cuenta_numero

        afp_id = parse_int(request.form.get("afp_id"))
        salud_id = parse_int(request.form.get("salud_id"))
        caja_compensacion_id = parse_int(request.form.get("caja_compensacion_id"))

        uf_plan_salud = parse_decimal(request.form.get("uf_plan_salud"))

        apv_activo = is_checked("apv_activo")
        apv_modalidad = request.form.get("apv_modalidad") or None
        apv_valor = parse_decimal(request.form.get("apv_valor"))
        apv_institucion = request.form.get("apv_institucion") or None
        if not apv_activo:
            apv_modalidad = None
            apv_valor = None
            apv_institucion = None

        cav_activo = is_checked("cav_activo")
        cav_modalidad = request.form.get("cav_modalidad") or None
        cav_valor = parse_decimal(request.form.get("cav_valor"))
        cav_institucion = request.form.get("cav_institucion") or None
        if not cav_activo:
            cav_modalidad = None
            cav_valor = None
            cav_institucion = None

        num_cargas_familiares = parse_int(request.form.get("num_cargas_familiares"))

        es_extranjero = is_checked("es_extranjero")
        es_discapacitado = is_checked("es_discapacitado")
        es_pensionado = is_checked("es_pensionado")

        tiene_examen_preocupacional = is_checked("tiene_examen_preocupacional")
        fecha_examen_preocupacional = parse_date(request.form.get("fecha_examen_preocupacional"))
        tiene_curso_altura = is_checked("tiene_curso_altura")
        fecha_vencimiento_curso_altura = parse_date(request.form.get("fecha_vencimiento_curso_altura"))
        tiene_induccion_obra = is_checked("tiene_induccion_obra")
        fecha_induccion_obra = parse_date(request.form.get("fecha_induccion_obra"))

        estado_trabajador = request.form.get("estado_trabajador") or "VIGENTE"
        tipo_trabajador = request.form.get("tipo_trabajador") or None
        fecha_ingreso_empresa = parse_date(request.form.get("fecha_ingreso_empresa"))
        fecha_egreso_empresa = parse_date(request.form.get("fecha_egreso_empresa"))

        trabajador.nombres = nombres
        trabajador.ap_paterno = ap_paterno
        trabajador.ap_materno = ap_materno

        trabajador.obra_id = obra_id
        trabajador.cargo_id = cargo_id

        trabajador.fecha_nacimiento = fecha_nacimiento
        trabajador.nacionalidad = nacionalidad
        trabajador.sexo = sexo
        trabajador.estado_civil = estado_civil

        trabajador.direccion = direccion
        trabajador.comuna = comuna
        trabajador.telefono = telefono
        trabajador.telefono_emergencia = telefono_emergencia
        trabajador.correo = correo

        trabajador.afp_id = afp_id
        trabajador.salud_id = salud_id
        trabajador.caja_compensacion_id = caja_compensacion_id
        trabajador.uf_plan_salud = uf_plan_salud

        trabajador.apv_activo = apv_activo
        trabajador.apv_modalidad = apv_modalidad
        trabajador.apv_valor = apv_valor
        trabajador.apv_institucion = apv_institucion

        trabajador.cav_activo = cav_activo
        trabajador.cav_modalidad = cav_modalidad
        trabajador.cav_valor = cav_valor
        trabajador.cav_institucion = cav_institucion

        trabajador.num_cargas_familiares = num_cargas_familiares
        trabajador.es_extranjero = es_extranjero
        trabajador.es_discapacitado = es_discapacitado
        trabajador.es_pensionado = es_pensionado

        trabajador.tiene_examen_preocupacional = tiene_examen_preocupacional
        trabajador.fecha_examen_preocupacional = fecha_examen_preocupacional
        trabajador.tiene_curso_altura = tiene_curso_altura
        trabajador.fecha_vencimiento_curso_altura = fecha_vencimiento_curso_altura
        trabajador.tiene_induccion_obra = tiene_induccion_obra
        trabajador.fecha_induccion_obra = fecha_induccion_obra

        trabajador.estado_trabajador = estado_trabajador
        trabajador.tipo_trabajador = tipo_trabajador
        trabajador.fecha_ingreso_empresa = fecha_ingreso_empresa
        trabajador.fecha_egreso_empresa = fecha_egreso_empresa

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

        next_url = request.args.get("next")
        if next_url:
            safe = _safe_next_url(next_url)
            if safe:
                return redirect(safe)

        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    allowed_obra_ids = _allowed_obra_ids_for_user()
    q_obras = Obra.query.filter_by(estado="ACTIVA")

    if allowed_obra_ids:
        q_obras = q_obras.filter(Obra.id.in_(allowed_obra_ids))

    obras = q_obras.order_by(Obra.nombre).all()

    bancos = Banco.query.order_by(Banco.nombre).all()
    afps = AFP.query.order_by(AFP.nombre).all()
    salud_list = Salud.query.order_by(Salud.nombre).all()
    cajas = CajaCompensacion.query.order_by(CajaCompensacion.nombre).all()
    cargos = Cargo.query.order_by(Cargo.id).all()

    rut_formateado = trabajador_rut_formateado(trabajador)

    return render_template(
        "trabajadores/trabajador_editar.html",
        trabajador=trabajador,
        obras=obras,
        bancos=bancos,
        afps=afps,
        salud_list=salud_list,
        cajas=cajas,
        cargos=cargos,
        rut_formateado=rut_formateado,
    )


# ===========================
# NUEVO TRABAJADOR
# ===========================

@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_trabajador():
    if request.method == "POST":
        accion = request.form.get("accion") or "guardar"

        next_url = (request.form.get("next") or request.args.get("next") or "").strip() or None
        next_url = _safe_next_url(next_url)

        rut_input = request.form.get("rut")
        nombres = request.form.get("nombres")
        ap_paterno = request.form.get("ap_paterno")
        ap_materno = (request.form.get("ap_materno") or "").strip() or None

        obra_id = parse_int(request.form.get("obra_id"))
        _enforce_access_to_obra(obra_id)

        cargo_id = parse_int(request.form.get("cargo_id"))

        if not obra_id:
            flash("Debes seleccionar una obra.", "error")
            return redirect(url_for("trabajadores.nuevo_trabajador", next=next_url) if next_url else url_for("trabajadores.nuevo_trabajador"))

        if not cargo_id:
            flash("Debes seleccionar un cargo.", "error")
            return redirect(url_for("trabajadores.nuevo_trabajador", next=next_url) if next_url else url_for("trabajadores.nuevo_trabajador"))

        if not (rut_input and nombres and ap_paterno):
            flash("Completa RUT, nombres y apellido paterno.", "error")
            return redirect(url_for("trabajadores.nuevo_trabajador", next=next_url) if next_url else url_for("trabajadores.nuevo_trabajador"))

        rut_digits, dv = split_rut(rut_input)
        if not rut_digits or not dv:
            flash("RUT inválido. Debe incluir dígito verificador (ej: 12.345.678-9).", "error")
            return redirect(url_for("trabajadores.nuevo_trabajador", next=next_url) if next_url else url_for("trabajadores.nuevo_trabajador"))

        fecha_nacimiento = parse_date(request.form.get("fecha_nacimiento"))
        nacionalidad = request.form.get("nacionalidad") or None
        sexo = request.form.get("sexo") or None
        estado_civil = request.form.get("estado_civil") or None

        direccion = request.form.get("direccion") or None
        comuna = request.form.get("comuna") or None
        telefono = request.form.get("telefono") or None
        telefono_emergencia = request.form.get("telefono_emergencia") or None
        correo = request.form.get("correo") or None

        banco_id = parse_int(request.form.get("banco_id"))
        tipo_cuenta = request.form.get("tipo_cuenta") or None
        cuenta_numero = request.form.get("cuenta_numero") or None

        cuenta_rut = None
        if tipo_cuenta == "CTA_RUT":
            cuenta_numero = rut_digits or None
            cuenta_rut = rut_digits or None
        else:
            cuenta_numero = cuenta_numero or None

        pago_tercero_activo = is_checked("pago_tercero_activo")
        pago_tercero_rut = request.form.get("pago_tercero_rut") or None
        pago_tercero_nombre = request.form.get("pago_tercero_nombre") or None
        pago_tercero_banco_id = parse_int(request.form.get("pago_tercero_banco_id"))
        pago_tercero_tipo_cuenta = request.form.get("pago_tercero_tipo_cuenta") or None
        pago_tercero_cuenta_numero = request.form.get("pago_tercero_cuenta_numero") or None

        if not pago_tercero_activo:
            pago_tercero_rut = None
            pago_tercero_nombre = None
            pago_tercero_banco_id = None
            pago_tercero_tipo_cuenta = None
            pago_tercero_cuenta_numero = None

        afp_id = parse_int(request.form.get("afp_id"))
        salud_id = parse_int(request.form.get("salud_id"))
        caja_compensacion_id = parse_int(request.form.get("caja_compensacion_id"))

        uf_plan_salud = parse_decimal(request.form.get("uf_plan_salud"))

        apv_activo = is_checked("apv_activo")
        apv_modalidad = request.form.get("apv_modalidad") or None
        apv_valor = parse_decimal(request.form.get("apv_valor"))
        apv_institucion = request.form.get("apv_institucion") or None
        if not apv_activo:
            apv_modalidad = None
            apv_valor = None
            apv_institucion = None

        cav_activo = is_checked("cav_activo")
        cav_modalidad = request.form.get("cav_modalidad") or None
        cav_valor = parse_decimal(request.form.get("cav_valor"))
        cav_institucion = request.form.get("cav_institucion") or None
        if not cav_activo:
            cav_modalidad = None
            cav_valor = None
            cav_institucion = None

        num_cargas_familiares = parse_int(request.form.get("num_cargas_familiares"))

        es_extranjero = is_checked("es_extranjero")
        es_discapacitado = is_checked("es_discapacitado")
        es_pensionado = is_checked("es_pensionado")

        tiene_examen_preocupacional = is_checked("tiene_examen_preocupacional")
        fecha_examen_preocupacional = parse_date(request.form.get("fecha_examen_preocupacional"))
        tiene_curso_altura = is_checked("tiene_curso_altura")
        fecha_vencimiento_curso_altura = parse_date(request.form.get("fecha_vencimiento_curso_altura"))
        tiene_induccion_obra = is_checked("tiene_induccion_obra")
        fecha_induccion_obra = parse_date(request.form.get("fecha_induccion_obra"))

        estado_trabajador = request.form.get("estado_trabajador") or "VIGENTE"
        tipo_trabajador = request.form.get("tipo_trabajador") or None
        fecha_ingreso_empresa = parse_date(request.form.get("fecha_ingreso_empresa"))
        fecha_egreso_empresa = parse_date(request.form.get("fecha_egreso_empresa"))

        t = Trabajador(
            rut=rut_digits,
            nombres=nombres,
            ap_paterno=ap_paterno,
            ap_materno=ap_materno,
            obra_id=obra_id,
            cargo_id=cargo_id,

            fecha_nacimiento=fecha_nacimiento,
            nacionalidad=nacionalidad,
            sexo=sexo,
            estado_civil=estado_civil,

            direccion=direccion,
            comuna=comuna,
            telefono=telefono,
            telefono_emergencia=telefono_emergencia,
            correo=correo,

            banco_id=banco_id,
            tipo_cuenta=tipo_cuenta,
            cuenta_rut=cuenta_rut,
            cuenta_numero=cuenta_numero,

            pago_tercero_activo=pago_tercero_activo,
            pago_tercero_rut=pago_tercero_rut,
            pago_tercero_nombre=pago_tercero_nombre,
            pago_tercero_banco_id=pago_tercero_banco_id,
            pago_tercero_tipo_cuenta=pago_tercero_tipo_cuenta,
            pago_tercero_cuenta_numero=pago_tercero_cuenta_numero,

            afp_id=afp_id,
            salud_id=salud_id,
            caja_compensacion_id=caja_compensacion_id,
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

        if hasattr(t, "dv"):
            t.dv = dv

        db.session.add(t)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "No se pudo registrar el trabajador. Verifica que el RUT no esté ya registrado y revisa los datos ingresados.",
                "error",
            )
            return redirect(url_for("trabajadores.nuevo_trabajador", next=next_url) if next_url else url_for("trabajadores.nuevo_trabajador"))

        flash("Trabajador registrado correctamente.", "success")

        if accion == "guardar":
            if next_url:
                return redirect(next_url)
            return redirect(url_for("trabajadores.listado_trabajadores"))

        if accion == "guardar_crear_contrato":
            return redirect(url_for("contratos.nuevo_contrato", trabajador_id=t.id, next=next_url))

        if next_url:
            return redirect(next_url)
        return redirect(url_for("trabajadores.listado_trabajadores"))

    allowed_obra_ids = _allowed_obra_ids_for_user()
    q_obras = Obra.query.filter_by(estado="ACTIVA")

    if allowed_obra_ids:
        q_obras = q_obras.filter(Obra.id.in_(allowed_obra_ids))

    obras = q_obras.order_by(Obra.nombre).all()

    if not obras:
        flash("Primero debes crear al menos una obra antes de registrar trabajadores.")
        return redirect(url_for("obras.lista_obras"))

    bancos = Banco.query.order_by(Banco.nombre).all()
    afps = AFP.query.order_by(AFP.nombre).all()
    salud_list = Salud.query.order_by(Salud.nombre).all()
    cajas = CajaCompensacion.query.order_by(CajaCompensacion.nombre).all()
    cargos = Cargo.query.order_by(Cargo.id).all()

    return render_template(
        "trabajadores/nuevo_trabajador.html",
        obras=obras,
        bancos=bancos,
        afps=afps,
        salud_list=salud_list,
        cajas=cajas,
        cargos=cargos,
    )
