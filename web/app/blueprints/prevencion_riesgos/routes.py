# web/app/blueprints/prevencion_riesgos/routes.py
from __future__ import annotations

from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from ...auth.decorators import role_required
from ...extensions import db
from ...common.dates import parse_date
from ...common.trabajadores import query_contratos_selector, contrato_selector_payload
from ...models import (
    Trabajador,
    Obra,
    Contrato,
    PrevTipoEPP,
    PrevEntregaEPP,
    PrevEntregaEPPItem,
    PrevCharlaSeguridad,
    PrevCharlaAsistente,
    PrevDocumentoPreventivo,
)
from . import bp
from .constants import (
    ROLES_PREVENCION_VER,
    ROLES_PREVENCION_EDITAR,
    TIPOS_CHARLA,
    TIPOS_DOCUMENTO_PREVENTIVO,
    ESTADOS_DOCUMENTO_PREVENTIVO,
)
from .queries import dashboard_counts, matriz_preventiva_rows, obras_accesibles_query, empleadores_accesibles_query, trabajadores_vigentes_query
from .services import seed_tipos_epp_iniciales
from .validators import validar_obra_accesible


def _estado_documento_por_fecha(fecha_vencimiento):
    if not fecha_vencimiento:
        return "VIGENTE"

    today = date.today()
    if fecha_vencimiento < today:
        return "VENCIDO"

    if fecha_vencimiento <= today + timedelta(days=30):
        return "POR_VENCER"

    return "VIGENTE"


def _estado_documento_desde_form(fecha_vencimiento, estado_manual: str | None = None):
    estado_manual = (estado_manual or "").strip().upper()

    if estado_manual == "ANULADO":
        return "ANULADO"

    if estado_manual == "PENDIENTE":
        return "PENDIENTE"

    return _estado_documento_por_fecha(fecha_vencimiento)



def _contratos_prevencion_query(user, obra_id: int | None = None):
    q = Contrato.query

    if hasattr(Contrato, "estado_contrato"):
        q = q.filter(Contrato.estado_contrato == "VIGENTE")

    if obra_id:
        q = q.filter(Contrato.obra_id == obra_id)

    if not user.has_role("ADMIN"):
        obra_ids = [o.id for o in getattr(user, "obras", []) or []]
        q = q.filter(Contrato.obra_id.in_(obra_ids or [-1]))

    return q.order_by(Contrato.id.desc())


def _contrato_accesible(user, contrato_id: int | None):
    if not contrato_id:
        return None

    contrato = Contrato.query.get(contrato_id)
    if not contrato:
        return None

    if not validar_obra_accesible(user, getattr(contrato, "obra_id", None)):
        return None

    return contrato





@bp.get("/api/contratos")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def api_contratos_selector():
    q = (request.args.get("q") or "").strip()
    limit_raw = request.args.get("limit") or "25"

    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 25

    limit = max(1, min(limit, 50))

    if len(q) < 2:
        return jsonify({"items": []})

    contratos = query_contratos_selector(current_user, q=q, limit=limit).all()

    return jsonify({
        "items": [contrato_selector_payload(contrato) for contrato in contratos]
    })




@bp.get("/")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def dashboard():
    stats = dashboard_counts(current_user)
    return render_template("prevencion_riesgos/dashboard.html", stats=stats)


@bp.get("/matriz")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def matriz():
    obra_id_raw = request.args.get("obra_id") or ""
    empleador_id_raw = request.args.get("empleador_id") or ""
    trabajador_q = (request.args.get("q") or "").strip()

    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None
    empleador_id = int(empleador_id_raw) if empleador_id_raw.isdigit() else None

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.matriz"))

    obras = obras_accesibles_query(current_user).all()
    empleadores = empleadores_accesibles_query(current_user).all()

    rows = matriz_preventiva_rows(
        current_user,
        obra_id=obra_id,
        empleador_id=empleador_id,
        trabajador_q=trabajador_q,
    )

    return render_template(
        "prevencion_riesgos/matriz.html",
        rows=rows,
        obras=obras,
        empleadores=empleadores,
        obra_id=obra_id,
        empleador_id=empleador_id,
        trabajador_q=trabajador_q,
    )

@bp.post("/admin/seed-epp")
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def seed_epp():
    creados = seed_tipos_epp_iniciales()
    if creados:
        flash(f"Se crearon {creados} tipos de EPP iniciales.", "success")
    else:
        flash("Los tipos de EPP iniciales ya estaban creados.", "info")
    return redirect(url_for("prevencion_riesgos.dashboard"))


@bp.get("/epp/tipos")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def tipos_epp():
    tipos = PrevTipoEPP.query.order_by(PrevTipoEPP.activo.desc(), PrevTipoEPP.nombre.asc()).all()
    return render_template("prevencion_riesgos/tipos_epp.html", tipos=tipos)


@bp.get("/epp")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def epp_listado():
    obra_id_raw = request.args.get("obra_id") or ""
    trabajador_q = (request.args.get("q") or "").strip()
    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.epp_listado"))

    q = PrevEntregaEPP.query

    if obra_id:
        q = q.filter(PrevEntregaEPP.obra_id == obra_id)

    if trabajador_q:
        like = f"%{trabajador_q}%"
        q = (
            q.join(Trabajador, Trabajador.id == PrevEntregaEPP.trabajador_id)
            .filter(
                or_(
                    Trabajador.nombres.ilike(like),
                    Trabajador.ap_paterno.ilike(like),
                    Trabajador.ap_materno.ilike(like),
                    Trabajador.rut.ilike(like),
                )
            )
        )

    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in getattr(current_user, "obras", []) or []]
        q = q.filter(PrevEntregaEPP.obra_id.in_(obra_ids or [-1]))

    entregas = (
        q.order_by(PrevEntregaEPP.fecha_entrega.desc(), PrevEntregaEPP.id.desc())
        .limit(300)
        .all()
    )

    obras = obras_accesibles_query(current_user).all()

    return render_template(
        "prevencion_riesgos/epp_listado.html",
        entregas=entregas,
        obras=obras,
        obra_id=obra_id,
        trabajador_q=trabajador_q,
    )


@bp.route("/epp/nueva", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def epp_nueva():
    if request.method == "GET":
        trabajadores = trabajadores_vigentes_query(current_user).limit(500).all()
        obras = obras_accesibles_query(current_user).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()
        tipos_epp = PrevTipoEPP.query.filter_by(activo=True).order_by(PrevTipoEPP.nombre.asc()).all()

        return render_template(
            "prevencion_riesgos/epp_form.html",
            trabajadores=trabajadores,
            obras=obras,
            contratos=contratos,
            tipos_epp=tipos_epp,
            today=date.today(),
        )

    trabajador_id = int(request.form.get("trabajador_id") or 0)
    obra_id = int(request.form.get("obra_id") or 0)
    contrato_id = int(request.form.get("contrato_id") or 0)
    fecha_entrega = parse_date(request.form.get("fecha_entrega"))
    observacion = (request.form.get("observacion") or "").strip() or None

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    if not obra_id:
        flash("Debes seleccionar una obra.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    if not fecha_entrega:
        flash("Debes indicar una fecha de entrega válida.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    contrato = _contrato_accesible(current_user, contrato_id)
    if contrato:
        trabajador_id = contrato.trabajador_id
        obra_id = contrato.obra_id

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    trabajador = Trabajador.query.get(trabajador_id)
    obra = Obra.query.get(obra_id)

    if not trabajador:
        flash("El trabajador seleccionado no existe.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    if not obra:
        flash("La obra seleccionada no existe.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    tipo_ids = request.form.getlist("tipo_epp_id[]")
    cantidades = request.form.getlist("cantidad[]")
    tallas = request.form.getlist("talla[]")
    marcas = request.form.getlist("marca_modelo[]")
    fechas_repo = request.form.getlist("fecha_reposicion_sugerida[]")
    observaciones_item = request.form.getlist("item_observacion[]")

    items_validos = []

    for idx, tipo_id_raw in enumerate(tipo_ids):
        tipo_id = int(tipo_id_raw or 0)
        if not tipo_id:
            continue

        cantidad_raw = cantidades[idx] if idx < len(cantidades) else "1"
        try:
            cantidad = int(cantidad_raw or 1)
        except ValueError:
            cantidad = 1

        if cantidad <= 0:
            cantidad = 1

        tipo = PrevTipoEPP.query.get(tipo_id)
        if not tipo or not tipo.activo:
            continue

        fecha_repo = parse_date(fechas_repo[idx]) if idx < len(fechas_repo) else None

        items_validos.append({
            "tipo": tipo,
            "cantidad": cantidad,
            "talla": (tallas[idx].strip() if idx < len(tallas) and tallas[idx].strip() else None),
            "marca_modelo": (marcas[idx].strip() if idx < len(marcas) and marcas[idx].strip() else None),
            "fecha_reposicion_sugerida": fecha_repo,
            "observacion": (
                observaciones_item[idx].strip()
                if idx < len(observaciones_item) and observaciones_item[idx].strip()
                else None
            ),
        })

    if not items_validos:
        flash("Debes agregar al menos un EPP válido a la entrega.", "error")
        return redirect(url_for("prevencion_riesgos.epp_nueva"))

    entrega = PrevEntregaEPP(
        trabajador_id=trabajador.id,
        contrato_id=contrato.id if contrato else None,
        obra_id=obra.id,
        fecha_entrega=fecha_entrega,
        observacion=observacion,
        registrado_por_id=current_user.id,
    )
    db.session.add(entrega)
    db.session.flush()

    for item in items_validos:
        db.session.add(
            PrevEntregaEPPItem(
                entrega_id=entrega.id,
                tipo_epp_id=item["tipo"].id,
                cantidad=item["cantidad"],
                talla=item["talla"],
                marca_modelo=item["marca_modelo"],
                fecha_reposicion_sugerida=item["fecha_reposicion_sugerida"],
                observacion=item["observacion"],
            )
        )

    db.session.commit()

    flash("Entrega de EPP registrada correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.epp_detalle", entrega_id=entrega.id))


@bp.get("/epp/<int:entrega_id>")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def epp_detalle(entrega_id: int):
    entrega = PrevEntregaEPP.query.get_or_404(entrega_id)

    if not validar_obra_accesible(current_user, entrega.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/epp_detalle.html", entrega=entrega)



@bp.route("/epp/<int:entrega_id>/editar", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def epp_editar(entrega_id: int):
    entrega = PrevEntregaEPP.query.get_or_404(entrega_id)

    if not validar_obra_accesible(current_user, entrega.obra_id):
        abort(403)

    if request.method == "GET":
        trabajadores = trabajadores_vigentes_query(current_user).limit(500).all()
        obras = obras_accesibles_query(current_user).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()
        tipos_epp = PrevTipoEPP.query.filter_by(activo=True).order_by(PrevTipoEPP.nombre.asc()).all()

        return render_template(
            "prevencion_riesgos/epp_form.html",
            modo="editar",
            entrega=entrega,
            trabajadores=trabajadores,
            obras=obras,
            contratos=contratos,
            tipos_epp=tipos_epp,
            today=date.today(),
        )

    trabajador_id = int(request.form.get("trabajador_id") or 0)
    obra_id = int(request.form.get("obra_id") or 0)
    contrato_id = int(request.form.get("contrato_id") or 0)
    fecha_entrega = parse_date(request.form.get("fecha_entrega"))
    observacion = (request.form.get("observacion") or "").strip() or None

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    if not obra_id:
        flash("Debes seleccionar una obra.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    if not fecha_entrega:
        flash("Debes indicar una fecha de entrega válida.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    contrato = _contrato_accesible(current_user, contrato_id)
    if contrato:
        trabajador_id = contrato.trabajador_id
        obra_id = contrato.obra_id

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    trabajador = Trabajador.query.get(trabajador_id)
    obra = Obra.query.get(obra_id)

    if not trabajador:
        flash("El trabajador seleccionado no existe.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    if not obra:
        flash("La obra seleccionada no existe.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    tipo_ids = request.form.getlist("tipo_epp_id[]")
    cantidades = request.form.getlist("cantidad[]")
    tallas = request.form.getlist("talla[]")
    marcas = request.form.getlist("marca_modelo[]")
    fechas_repo = request.form.getlist("fecha_reposicion_sugerida[]")
    observaciones_item = request.form.getlist("item_observacion[]")

    items_validos = []

    for idx, tipo_id_raw in enumerate(tipo_ids):
        tipo_id = int(tipo_id_raw or 0)
        if not tipo_id:
            continue

        cantidad_raw = cantidades[idx] if idx < len(cantidades) else "1"
        try:
            cantidad = int(cantidad_raw or 1)
        except ValueError:
            cantidad = 1

        if cantidad <= 0:
            cantidad = 1

        tipo = PrevTipoEPP.query.get(tipo_id)
        if not tipo or not tipo.activo:
            continue

        fecha_repo = parse_date(fechas_repo[idx]) if idx < len(fechas_repo) else None

        items_validos.append({
            "tipo": tipo,
            "cantidad": cantidad,
            "talla": (tallas[idx].strip() if idx < len(tallas) and tallas[idx].strip() else None),
            "marca_modelo": (marcas[idx].strip() if idx < len(marcas) and marcas[idx].strip() else None),
            "fecha_reposicion_sugerida": fecha_repo,
            "observacion": (
                observaciones_item[idx].strip()
                if idx < len(observaciones_item) and observaciones_item[idx].strip()
                else None
            ),
        })

    if not items_validos:
        flash("Debes agregar al menos un EPP válido a la entrega.", "error")
        return redirect(url_for("prevencion_riesgos.epp_editar", entrega_id=entrega.id))

    entrega.trabajador_id = trabajador.id
    entrega.contrato_id = contrato.id if contrato else None
    entrega.obra_id = obra.id
    entrega.fecha_entrega = fecha_entrega
    entrega.observacion = observacion

    # Reemplazamos items para mantener consistencia con el formulario dinámico.
    PrevEntregaEPPItem.query.filter_by(entrega_id=entrega.id).delete()

    for item in items_validos:
        db.session.add(
            PrevEntregaEPPItem(
                entrega_id=entrega.id,
                tipo_epp_id=item["tipo"].id,
                cantidad=item["cantidad"],
                talla=item["talla"],
                marca_modelo=item["marca_modelo"],
                fecha_reposicion_sugerida=item["fecha_reposicion_sugerida"],
                observacion=item["observacion"],
            )
        )

    db.session.commit()

    flash("Entrega de EPP actualizada correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.epp_detalle", entrega_id=entrega.id))


@bp.get("/epp/<int:entrega_id>/imprimir")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def epp_imprimir(entrega_id: int):
    entrega = PrevEntregaEPP.query.get_or_404(entrega_id)

    if not validar_obra_accesible(current_user, entrega.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/epp_imprimir.html", entrega=entrega)


@bp.get("/charlas")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def charlas_listado():
    obra_id_raw = request.args.get("obra_id") or ""
    q_text = (request.args.get("q") or "").strip()
    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.charlas_listado"))

    q = PrevCharlaSeguridad.query

    if obra_id:
        q = q.filter(PrevCharlaSeguridad.obra_id == obra_id)

    if q_text:
        like = f"%{q_text}%"
        q = q.filter(
            or_(
                PrevCharlaSeguridad.titulo.ilike(like),
                PrevCharlaSeguridad.tipo.ilike(like),
                PrevCharlaSeguridad.relator.ilike(like),
                PrevCharlaSeguridad.tema.ilike(like),
            )
        )

    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in getattr(current_user, "obras", []) or []]
        q = q.filter(PrevCharlaSeguridad.obra_id.in_(obra_ids or [-1]))

    charlas = (
        q.order_by(PrevCharlaSeguridad.fecha.desc(), PrevCharlaSeguridad.id.desc())
        .limit(300)
        .all()
    )

    obras = obras_accesibles_query(current_user).all()

    return render_template(
        "prevencion_riesgos/charlas_listado.html",
        charlas=charlas,
        obras=obras,
        obra_id=obra_id,
        q_text=q_text,
    )


@bp.route("/charlas/nueva", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def charla_nueva():
    if request.method == "GET":
        obras = obras_accesibles_query(current_user).all()
        trabajadores = trabajadores_vigentes_query(current_user).limit(600).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()

        return render_template(
            "prevencion_riesgos/charla_form.html",
            obras=obras,
            trabajadores=trabajadores,
            contratos=contratos,
            asistentes_contrato_ids=set(),
            tipos_charla=TIPOS_CHARLA,
            today=date.today(),
        )

    obra_id = int(request.form.get("obra_id") or 0)
    titulo = (request.form.get("titulo") or "").strip()
    tipo = (request.form.get("tipo") or "").strip()
    fecha = parse_date(request.form.get("fecha"))
    relator = (request.form.get("relator") or "").strip() or None
    tema = (request.form.get("tema") or "").strip() or None
    observacion = (request.form.get("observacion") or "").strip() or None

    duracion_raw = (request.form.get("duracion_minutos") or "").strip()
    try:
        duracion_minutos = int(duracion_raw) if duracion_raw else None
    except ValueError:
        duracion_minutos = None

    contrato_ids = []
    for raw in request.form.getlist("contrato_ids"):
        try:
            contrato_ids.append(int(raw))
        except ValueError:
            continue

    if not obra_id:
        flash("Debes seleccionar una obra.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    if not titulo:
        flash("Debes indicar un título para la charla.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    if not tipo:
        flash("Debes seleccionar el tipo de charla.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    if not fecha:
        flash("Debes indicar una fecha válida.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    if not contrato_ids:
        flash("Debes seleccionar al menos un contrato/asistente.", "error")
        return redirect(url_for("prevencion_riesgos.charla_nueva"))

    charla = PrevCharlaSeguridad(
        obra_id=obra_id,
        titulo=titulo,
        tipo=tipo,
        fecha=fecha,
        relator=relator,
        duracion_minutos=duracion_minutos,
        tema=tema,
        observacion=observacion,
        registrado_por_id=current_user.id,
    )
    db.session.add(charla)
    db.session.flush()

    for contrato_id in sorted(set(contrato_ids)):
        contrato = _contrato_accesible(current_user, contrato_id)
        if not contrato:
            continue

        db.session.add(
            PrevCharlaAsistente(
                charla_id=charla.id,
                trabajador_id=contrato.trabajador_id,
                contrato_id=contrato.id,
                asistio=True,
            )
        )

    db.session.commit()

    flash("Charla de seguridad registrada correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.charla_detalle", charla_id=charla.id))


@bp.get("/charlas/<int:charla_id>")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def charla_detalle(charla_id: int):
    charla = PrevCharlaSeguridad.query.get_or_404(charla_id)

    if not validar_obra_accesible(current_user, charla.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/charla_detalle.html", charla=charla)



@bp.route("/charlas/<int:charla_id>/editar", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def charla_editar(charla_id: int):
    charla = PrevCharlaSeguridad.query.get_or_404(charla_id)

    if not validar_obra_accesible(current_user, charla.obra_id):
        abort(403)

    if request.method == "GET":
        obras = obras_accesibles_query(current_user).all()
        trabajadores = trabajadores_vigentes_query(current_user).limit(600).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()
        asistentes_ids = {
            asistente.trabajador_id
            for asistente in charla.asistentes
            if asistente.asistio
        }
        asistentes_contrato_ids = {
            asistente.contrato_id
            for asistente in charla.asistentes
            if asistente.asistio and asistente.contrato_id
        }

        return render_template(
            "prevencion_riesgos/charla_form.html",
            modo="editar",
            charla=charla,
            obras=obras,
            trabajadores=trabajadores,
            contratos=contratos,
            asistentes_ids=asistentes_ids,
            asistentes_contrato_ids=asistentes_contrato_ids,
            tipos_charla=TIPOS_CHARLA,
            today=date.today(),
        )

    obra_id = int(request.form.get("obra_id") or 0)
    titulo = (request.form.get("titulo") or "").strip()
    tipo = (request.form.get("tipo") or "").strip()
    fecha = parse_date(request.form.get("fecha"))
    relator = (request.form.get("relator") or "").strip() or None
    tema = (request.form.get("tema") or "").strip() or None
    observacion = (request.form.get("observacion") or "").strip() or None

    duracion_raw = (request.form.get("duracion_minutos") or "").strip()
    try:
        duracion_minutos = int(duracion_raw) if duracion_raw else None
    except ValueError:
        duracion_minutos = None

    contrato_ids = []
    for raw in request.form.getlist("contrato_ids"):
        try:
            contrato_ids.append(int(raw))
        except ValueError:
            continue

    if not obra_id:
        flash("Debes seleccionar una obra.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    if not titulo:
        flash("Debes indicar un título para la charla.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    if not tipo:
        flash("Debes seleccionar el tipo de charla.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    if not fecha:
        flash("Debes indicar una fecha válida.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    if not contrato_ids:
        flash("Debes seleccionar al menos un contrato/asistente.", "error")
        return redirect(url_for("prevencion_riesgos.charla_editar", charla_id=charla.id))

    charla.obra_id = obra_id
    charla.titulo = titulo
    charla.tipo = tipo
    charla.fecha = fecha
    charla.relator = relator
    charla.duracion_minutos = duracion_minutos
    charla.tema = tema
    charla.observacion = observacion

    # Reemplazamos asistentes para mantener el registro simple y consistente.
    PrevCharlaAsistente.query.filter_by(charla_id=charla.id).delete()

    for contrato_id in sorted(set(contrato_ids)):
        contrato = _contrato_accesible(current_user, contrato_id)
        if not contrato:
            continue

        db.session.add(
            PrevCharlaAsistente(
                charla_id=charla.id,
                trabajador_id=contrato.trabajador_id,
                contrato_id=contrato.id,
                asistio=True,
            )
        )

    db.session.commit()

    flash("Charla de seguridad actualizada correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.charla_detalle", charla_id=charla.id))


@bp.get("/charlas/<int:charla_id>/imprimir")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def charla_imprimir(charla_id: int):
    charla = PrevCharlaSeguridad.query.get_or_404(charla_id)

    if not validar_obra_accesible(current_user, charla.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/charla_imprimir.html", charla=charla)


@bp.get("/documentos")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def documentos_listado():
    obra_id_raw = request.args.get("obra_id") or ""
    trabajador_q = (request.args.get("q") or "").strip()
    tipo_documento = (request.args.get("tipo_documento") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None

    if not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.documentos_listado"))

    q = PrevDocumentoPreventivo.query

    if obra_id:
        q = q.filter(PrevDocumentoPreventivo.obra_id == obra_id)

    if tipo_documento:
        q = q.filter(PrevDocumentoPreventivo.tipo_documento == tipo_documento)

    if estado:
        q = q.filter(PrevDocumentoPreventivo.estado == estado)

    if trabajador_q:
        like = f"%{trabajador_q}%"
        q = (
            q.join(Trabajador, Trabajador.id == PrevDocumentoPreventivo.trabajador_id)
            .filter(
                or_(
                    Trabajador.nombres.ilike(like),
                    Trabajador.ap_paterno.ilike(like),
                    Trabajador.ap_materno.ilike(like),
                    Trabajador.rut.ilike(like),
                )
            )
        )

    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in getattr(current_user, "obras", []) or []]
        q = q.filter(PrevDocumentoPreventivo.obra_id.in_(obra_ids or [-1]))

    documentos = (
        q.order_by(
            PrevDocumentoPreventivo.fecha_vencimiento.asc().nulls_last(),
            PrevDocumentoPreventivo.fecha_emision.desc(),
            PrevDocumentoPreventivo.id.desc(),
        )
        .limit(400)
        .all()
    )

    obras = obras_accesibles_query(current_user).all()

    return render_template(
        "prevencion_riesgos/documentos_listado.html",
        documentos=documentos,
        obras=obras,
        obra_id=obra_id,
        trabajador_q=trabajador_q,
        tipo_documento=tipo_documento,
        estado=estado,
        tipos_documento=TIPOS_DOCUMENTO_PREVENTIVO,
        estados_documento=ESTADOS_DOCUMENTO_PREVENTIVO,
    )


@bp.route("/documentos/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def documento_nuevo():
    if request.method == "GET":
        trabajadores = trabajadores_vigentes_query(current_user).limit(600).all()
        obras = obras_accesibles_query(current_user).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()

        return render_template(
            "prevencion_riesgos/documento_form.html",
            modo="crear",
            doc=None,
            trabajadores=trabajadores,
            obras=obras,
            contratos=contratos,
            tipos_documento=TIPOS_DOCUMENTO_PREVENTIVO,
            estados_documento=ESTADOS_DOCUMENTO_PREVENTIVO,
            today=date.today(),
        )

    trabajador_id = int(request.form.get("trabajador_id") or 0)
    obra_id_raw = request.form.get("obra_id") or ""
    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None
    contrato_id = int(request.form.get("contrato_id") or 0)
    tipo_documento = (request.form.get("tipo_documento") or "").strip()
    fecha_emision = parse_date(request.form.get("fecha_emision"))
    fecha_vencimiento = parse_date(request.form.get("fecha_vencimiento"))
    archivo_nombre = (request.form.get("archivo_nombre") or "").strip() or None
    archivo_path = (request.form.get("archivo_path") or "").strip() or None
    observacion = (request.form.get("observacion") or "").strip() or None

    contrato = _contrato_accesible(current_user, contrato_id)
    if contrato:
        trabajador_id = contrato.trabajador_id
        obra_id = contrato.obra_id

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    if obra_id is not None and not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    if not tipo_documento:
        flash("Debes seleccionar el tipo de documento.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    if not fecha_emision:
        flash("Debes indicar una fecha de emisión válida.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    if fecha_vencimiento and fecha_vencimiento < fecha_emision:
        flash("La fecha de vencimiento no puede ser anterior a la fecha de emisión.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    trabajador = Trabajador.query.get(trabajador_id)
    if not trabajador:
        flash("El trabajador seleccionado no existe.", "error")
        return redirect(url_for("prevencion_riesgos.documento_nuevo"))

    if obra_id is None:
        obra_id = getattr(trabajador, "obra_id", None)

    estado = _estado_documento_por_fecha(fecha_vencimiento)

    doc = PrevDocumentoPreventivo(
        trabajador_id=trabajador.id,
        contrato_id=contrato.id if contrato else None,
        obra_id=obra_id,
        tipo_documento=tipo_documento,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        estado=estado,
        archivo_nombre=archivo_nombre,
        archivo_path=archivo_path,
        observacion=observacion,
        registrado_por_id=current_user.id,
    )

    db.session.add(doc)
    db.session.commit()

    flash("Documento preventivo registrado correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.documento_detalle", documento_id=doc.id))


@bp.get("/documentos/<int:documento_id>")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def documento_detalle(documento_id: int):
    doc = PrevDocumentoPreventivo.query.get_or_404(documento_id)

    if doc.obra_id is not None and not validar_obra_accesible(current_user, doc.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/documento_detalle.html", doc=doc)


@bp.route("/documentos/<int:documento_id>/editar", methods=["GET", "POST"])
@login_required
@role_required(*ROLES_PREVENCION_EDITAR)
def documento_editar(documento_id: int):
    doc = PrevDocumentoPreventivo.query.get_or_404(documento_id)

    if doc.obra_id is not None and not validar_obra_accesible(current_user, doc.obra_id):
        abort(403)

    if request.method == "GET":
        trabajadores = trabajadores_vigentes_query(current_user).limit(600).all()
        obras = obras_accesibles_query(current_user).all()
        contratos = _contratos_prevencion_query(current_user).limit(800).all()

        return render_template(
            "prevencion_riesgos/documento_form.html",
            modo="editar",
            doc=doc,
            trabajadores=trabajadores,
            obras=obras,
            contratos=contratos,
            tipos_documento=TIPOS_DOCUMENTO_PREVENTIVO,
            estados_documento=ESTADOS_DOCUMENTO_PREVENTIVO,
            today=date.today(),
        )

    trabajador_id = int(request.form.get("trabajador_id") or 0)
    obra_id_raw = request.form.get("obra_id") or ""
    obra_id = int(obra_id_raw) if obra_id_raw.isdigit() else None
    contrato_id = int(request.form.get("contrato_id") or 0)
    tipo_documento = (request.form.get("tipo_documento") or "").strip()
    fecha_emision = parse_date(request.form.get("fecha_emision"))
    fecha_vencimiento = parse_date(request.form.get("fecha_vencimiento"))
    estado_manual = (request.form.get("estado") or "").strip()
    archivo_nombre = (request.form.get("archivo_nombre") or "").strip() or None
    archivo_path = (request.form.get("archivo_path") or "").strip() or None
    observacion = (request.form.get("observacion") or "").strip() or None

    contrato = _contrato_accesible(current_user, contrato_id)
    if contrato:
        trabajador_id = contrato.trabajador_id
        obra_id = contrato.obra_id

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    if obra_id is not None and not validar_obra_accesible(current_user, obra_id):
        flash("No tienes acceso a la obra seleccionada.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    if not tipo_documento:
        flash("Debes seleccionar el tipo de documento.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    if not fecha_emision:
        flash("Debes indicar una fecha de emisión válida.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    if fecha_vencimiento and fecha_vencimiento < fecha_emision:
        flash("La fecha de vencimiento no puede ser anterior a la fecha de emisión.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    trabajador = Trabajador.query.get(trabajador_id)
    if not trabajador:
        flash("El trabajador seleccionado no existe.", "error")
        return redirect(url_for("prevencion_riesgos.documento_editar", documento_id=doc.id))

    if obra_id is None:
        obra_id = getattr(trabajador, "obra_id", None)

    doc.trabajador_id = trabajador.id
    doc.contrato_id = contrato.id if contrato else None
    doc.obra_id = obra_id
    doc.tipo_documento = tipo_documento
    doc.fecha_emision = fecha_emision
    doc.fecha_vencimiento = fecha_vencimiento
    doc.estado = _estado_documento_desde_form(fecha_vencimiento, estado_manual)
    doc.archivo_nombre = archivo_nombre
    doc.archivo_path = archivo_path
    doc.observacion = observacion

    db.session.commit()

    flash("Documento preventivo actualizado correctamente.", "success")
    return redirect(url_for("prevencion_riesgos.documento_detalle", documento_id=doc.id))


@bp.get("/documentos/<int:documento_id>/imprimir")
@login_required
@role_required(*ROLES_PREVENCION_VER)
def documento_imprimir(documento_id: int):
    doc = PrevDocumentoPreventivo.query.get_or_404(documento_id)

    if doc.obra_id is not None and not validar_obra_accesible(current_user, doc.obra_id):
        abort(403)

    return render_template("prevencion_riesgos/documento_imprimir.html", doc=doc)
