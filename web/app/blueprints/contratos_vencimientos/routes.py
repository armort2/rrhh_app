from __future__ import annotations

from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy import or_, func
import sqlalchemy as sa

from ...auth.decorators import role_required
from ...extensions import db
from ...models import (
    Contrato,
    Trabajador,
    Obra,
    Empleador,
    Cargo,
    ContratoVencimientoDecision,
    AnexoExtensionContrato,
)
from ..contratos.routes import aplicar_filtro_obras_autorizadas_a_contratos  # reutilizamos helper
from . import bp


ACCIONES = ("PENDIENTE", "EXTENDER", "TERMINAR", "INDEFINIDO")


def _parse_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _parse_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        # input type=date => YYYY-MM-DD
        y, m, d = v.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


@bp.get("/")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    # ---------------------------
    # Filtros (ventana por vencer)
    # ---------------------------
    dias = _parse_int(request.args.get("dias"), 30) or 30
    dias = max(1, min(dias, 365))

    centro_costos = request.args.getlist("centro_costo")
    centro_costos = [cc.strip() for cc in centro_costos if (cc or "").strip()]

    accion = (request.args.get("accion") or "").strip().upper() or ""
    if accion and accion not in ACCIONES:
        accion = ""

    hoy = date.today()
    hasta = hoy + timedelta(days=dias)

    query = (
        Contrato.query
        .join(Trabajador, Contrato.trabajador_id == Trabajador.id)
        .join(Obra, Contrato.obra_id == Obra.id)
        .outerjoin(Empleador, Contrato.empleador_id == Empleador.id)
        .outerjoin(Cargo, Contrato.cargo_id == Cargo.id)
        .filter(
            Contrato.estado_contrato == "VIGENTE",
            Contrato.fecha_termino.isnot(None),
            Contrato.fecha_termino >= hoy,
            Contrato.fecha_termino <= hasta,
        )
    )

    # ✅ filtro obras autorizadas
    query = aplicar_filtro_obras_autorizadas_a_contratos(query)

    # ✅ filtro por Centro de Costo
    if centro_costos:
        query = query.filter(Obra.centro_costo.in_(centro_costos))

    contratos = (
        query.order_by(
            Obra.nombre,
            Contrato.fecha_termino.asc(),
            Trabajador.ap_paterno,
            Trabajador.ap_materno,
        ).all()
    )

    contrato_ids = [c.id for c in contratos]

    # ✅ contratos que YA tienen anexo de extensión (no se puede volver a extender)
    contratos_extendidos = set()
    if contrato_ids:
        rows = (
            db.session.query(AnexoExtensionContrato.contrato_id)
            .filter(AnexoExtensionContrato.contrato_id.in_(contrato_ids))
            .distinct()
            .all()
        )
        contratos_extendidos = {r[0] for r in rows if r and r[0]}

    decisiones = {}
    if contrato_ids:
        ds = (
            ContratoVencimientoDecision.query
            .filter(ContratoVencimientoDecision.contrato_id.in_(contrato_ids))
            .all()
        )
        decisiones = {d.contrato_id: d for d in ds}

    # Filtro por accion (aplicado a decisiones, no a contratos)
    if accion:
        contratos = [
            c for c in contratos
            if (decisiones.get(c.id).accion if decisiones.get(c.id) else "PENDIENTE") == accion
        ]

    # ✅ Lista de Centros de Costo disponibles (según permisos)
    if current_user.has_role("ADMIN"):
        centros_costos = (
            db.session.query(Obra.centro_costo)
            .filter(Obra.estado == "ACTIVA", Obra.centro_costo.isnot(None))
            .distinct()
            .order_by(Obra.centro_costo.asc())
            .all()
        )
        centros_costos = [r[0] for r in centros_costos if r[0]]
    else:
        ccs = []
        for o in (current_user.obras or []):
            if o and o.estado == "ACTIVA" and (o.centro_costo or "").strip():
                ccs.append(o.centro_costo.strip())
        centros_costos = sorted(set(ccs))

    # ---------------------------
    # Acciones extraordinarias
    # (decisiones sobre contratos que NO están en la ventana por vencer)
    # ---------------------------
    extra_limit = 50

    extra_q = (
        ContratoVencimientoDecision.query
        .join(Contrato, ContratoVencimientoDecision.contrato_id == Contrato.id)
        .join(Trabajador, Contrato.trabajador_id == Trabajador.id)
        .join(Obra, Contrato.obra_id == Obra.id)
        .outerjoin(Cargo, Contrato.cargo_id == Cargo.id)
        .filter(
            Contrato.estado_contrato == "VIGENTE",
            or_(
                Contrato.fecha_termino.is_(None),        # indefinidos típicamente
                Contrato.fecha_termino < hoy,            # ya vencidos (por si quieren registrar cierre)
                Contrato.fecha_termino > hasta,          # fuera de ventana
            ),
        )
        .order_by(ContratoVencimientoDecision.actualizado_en.desc())
        .limit(extra_limit)
    )

    # ✅ control de acceso por obra (reutilizamos helper sobre Contrato)
    extra_contrato_ids = [d.contrato_id for d in extra_q.all()]
    extra_contratos = []
    if extra_contrato_ids:
        cq = Contrato.query.filter(Contrato.id.in_(extra_contrato_ids))
        cq = aplicar_filtro_obras_autorizadas_a_contratos(cq)
        extra_contratos = cq.all()
        extra_contratos_map = {c.id: c for c in extra_contratos}

        # volvemos a pedir decisiones pero solo para los contratos accesibles
        extra_ds = (
            ContratoVencimientoDecision.query
            .filter(ContratoVencimientoDecision.contrato_id.in_(list(extra_contratos_map.keys())))
            .order_by(ContratoVencimientoDecision.actualizado_en.desc())
            .all()
        )
        decisiones_extra = {d.contrato_id: d for d in extra_ds}
        extra_contratos = sorted(
            extra_contratos,
            key=lambda c: (c.obra.nombre if c.obra and c.obra.nombre else "", c.trabajador.ap_paterno or ""),
        )
    else:
        decisiones_extra = {}

    return render_template(
        "contratos_vencimientos/listado.html",
        # ventana por vencer
        contratos=contratos,
        decisiones=decisiones,
        # extraordinarias
        extra_contratos=extra_contratos,
        decisiones_extra=decisiones_extra,
        extra_limit=extra_limit,
        # filtros
        centros_costos=centros_costos,
        filtro_dias=dias,
        filtro_centro_costos=centro_costos,
        filtro_accion=accion,
        hoy=hoy,
        hasta=hasta,
        ACCIONES=ACCIONES,
        contratos_extendidos=contratos_extendidos,
    )


@bp.post("/agregar")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def agregar():
    """
    Agrega un contrato al seguimiento "extraordinario".
    Útil para contratos indefinidos o que no están por vencer dentro de la ventana.
    """
    contrato_id = _parse_int(request.form.get("contrato_id"), None)
    if not contrato_id:
        flash("Debes indicar un ID de contrato válido.", "warning")
        return redirect(url_for("contratos_vencimientos.listado", **request.args))

    accion = (request.form.get("accion") or "TERMINAR").strip().upper()
    if accion not in ACCIONES:
        accion = "TERMINAR"

    nueva_fecha = _parse_date(request.form.get("nueva_fecha"))
    fecha_conf = _parse_date(request.form.get("fecha_conf"))
    comentario = (request.form.get("comentario") or "").strip() or None

    # contrato + control acceso por obra
    q = Contrato.query.filter(Contrato.id == contrato_id)
    q = aplicar_filtro_obras_autorizadas_a_contratos(q)
    c = q.first()

    if not c:
        flash("Contrato no encontrado o no tienes acceso a la obra asociada.", "danger")
        return redirect(url_for("contratos_vencimientos.listado", **request.args))

    if c.estado_contrato != "VIGENTE":
        flash("Solo puedes agregar contratos VIGENTES a este seguimiento.", "warning")
        return redirect(url_for("contratos_vencimientos.listado", **request.args))
    
    ya_extendio = (
        db.session.query(AnexoExtensionContrato.id)
        .filter(AnexoExtensionContrato.contrato_id == c.id)
        .first()
        is not None
    )

    if accion == "EXTENDER" and ya_extendio:
        flash("Este contrato ya tiene un anexo de extensión. No se puede volver a extender.", "warning")
        return redirect(url_for("contratos_vencimientos.listado", **request.args))

    # Validaciones de negocio
    if accion == "EXTENDER":
        if not nueva_fecha:
            flash("Para EXTENDER debes indicar la nueva fecha de término.", "warning")
            return redirect(url_for("contratos_vencimientos.listado", **request.args))
        if c.fecha_termino and nueva_fecha <= c.fecha_termino:
            flash("La nueva fecha debe ser mayor al término actual del contrato.", "warning")
            return redirect(url_for("contratos_vencimientos.listado", **request.args))

    if accion == "INDEFINIDO":
        nueva_fecha = None
        fecha_conf = None

    if accion == "PENDIENTE":
        nueva_fecha = None
        fecha_conf = None

    if accion == "TERMINAR":
        # Si no envían confirmada, sugerimos la actual del contrato si existe
        if not fecha_conf and c.fecha_termino:
            fecha_conf = c.fecha_termino
        # nueva_fecha no aplica
        nueva_fecha = None

    d = ContratoVencimientoDecision.query.filter_by(contrato_id=c.id).first()
    if not d:
        d = ContratoVencimientoDecision(
            contrato_id=c.id,
            obra_id=c.obra_id,
            empleador_id=c.empleador_id,
            trabajador_id=c.trabajador_id,
        )
        db.session.add(d)

    d.accion = accion
    d.nueva_fecha_termino = nueva_fecha
    d.fecha_termino_confirmada = fecha_conf
    d.comentario = comentario
    d.decidido_por_user_id = current_user.id

    db.session.commit()
    flash(f"Seguimiento agregado/actualizado para Contrato #{c.id}.", "success")
    return redirect(url_for("contratos_vencimientos.listado", **request.args))


@bp.post("/guardar")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def guardar():
    # ids enviados
    ids = request.form.getlist("contrato_id", type=int)
    if not ids:
        flash("No se enviaron contratos para guardar.", "warning")
        return redirect(url_for("contratos_vencimientos.listado"))

    # Traemos contratos y aplicamos control por obra
    q = Contrato.query.filter(Contrato.id.in_(ids))
    q = aplicar_filtro_obras_autorizadas_a_contratos(q)
    contratos = q.all()
    contratos_map = {c.id: c for c in contratos}

    # Cargamos decisiones existentes
    existentes = (
        ContratoVencimientoDecision.query
        .filter(ContratoVencimientoDecision.contrato_id.in_(list(contratos_map.keys())))
        .all()
    )
    dec_map = {d.contrato_id: d for d in existentes}

    updated = 0
    errores = 0

    extendidos = set()
    if contratos_map:
        rows = (
            db.session.query(AnexoExtensionContrato.contrato_id)
            .filter(AnexoExtensionContrato.contrato_id.in_(list(contratos_map.keys())))
            .distinct()
            .all()
        )
        extendidos = {r[0] for r in rows if r and r[0]}

    for cid, c in contratos_map.items():
        accion = (request.form.get(f"accion_{cid}") or "PENDIENTE").strip().upper()
        if accion not in ACCIONES:
            accion = "PENDIENTE"

        if accion == "EXTENDER" and cid in extendidos:
            errores += 1
            continue

        nueva_fecha = _parse_date(request.form.get(f"nueva_fecha_{cid}"))
        fecha_conf = _parse_date(request.form.get(f"fecha_conf_{cid}"))
        comentario = (request.form.get(f"comentario_{cid}") or "").strip() or None

        # Validaciones de negocio
        if accion == "EXTENDER":
            if not nueva_fecha:
                errores += 1
                continue
            if c.fecha_termino and nueva_fecha <= c.fecha_termino:
                errores += 1
                continue

        if accion == "TERMINAR":
            # Si no envían confirmada, dejamos NULL (se interpreta como “usar fecha actual del contrato”)
            pass

        if accion == "INDEFINIDO":
            nueva_fecha = None
            fecha_conf = None

        if accion == "PENDIENTE":
            nueva_fecha = None
            fecha_conf = None

        d = dec_map.get(cid)
        if not d:
            d = ContratoVencimientoDecision(
                contrato_id=cid,
                obra_id=c.obra_id,
                empleador_id=c.empleador_id,
                trabajador_id=c.trabajador_id,
            )
            db.session.add(d)

        d.accion = accion
        d.nueva_fecha_termino = nueva_fecha
        d.fecha_termino_confirmada = fecha_conf
        d.comentario = comentario
        d.decidido_por_user_id = current_user.id

        updated += 1

    db.session.commit()

    if updated:
        flash(f"Decisiones guardadas: {updated}.", "success")
    if errores:
        flash(
            "Ojo: "
            f"{errores} fila(s) no se guardaron por validación "
            "(ej: EXTENDER sin fecha o fecha <= término actual).",
            "warning",
        )

    return redirect(url_for("contratos_vencimientos.listado", **request.args))

from sqlalchemy.orm import joinedload

@bp.get("/api/contratos")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def api_contratos():
    """
    Devuelve contratos de un trabajador para selector (acciones extraordinarias).
    - Respeta permisos por obra (filtro corporativo).
    - Ordena vigentes primero, luego por fecha_inicio desc / id desc.
    - Limita a 20.
    """
    trabajador_id = request.args.get("trabajador_id", type=int)
    if not trabajador_id:
        return {"results": []}

    q = (
        Contrato.query
        .options(
            joinedload(Contrato.obra),
            joinedload(Contrato.cargo),
        )
        .filter(Contrato.trabajador_id == trabajador_id)
    )

    # ✅ control de acceso por obra (CRÍTICO)
    q = aplicar_filtro_obras_autorizadas_a_contratos(q)

    # Vigentes primero (si existe el campo)
    if hasattr(Contrato, "estado_contrato"):
        q = q.order_by(
            sa.case((Contrato.estado_contrato == "VIGENTE", 0), else_=1).asc()
        )

    # Orden operativo
    if hasattr(Contrato, "fecha_inicio"):
        q = q.order_by(Contrato.fecha_inicio.desc().nullslast())

    q = q.order_by(Contrato.id.desc()).limit(20)

    results = []
    for c in q.all():
        obra = getattr(c, "obra", None)
        cargo = getattr(c, "cargo", None)

        obra_nombre = getattr(obra, "nombre", "") or ""
        centro_costo = getattr(obra, "centro_costo", "") or ""
        cargo_nombre = getattr(cargo, "nombre", "") or ""
        estado = getattr(c, "estado_contrato", "") or ""

        ft = getattr(c, "fecha_termino", None)
        ft_txt = ft.strftime("%d-%m-%Y") if ft else "Indefinido"

        label = f"#{c.id} · {estado or '—'} · {ft_txt}"
        if cargo_nombre:
            label += f" · {cargo_nombre}"
        if centro_costo or obra_nombre:
            label += f" · {centro_costo} {obra_nombre}".strip()

        results.append({
            "id": c.id,
            "label": label,
            "estado": estado,
            "fecha_termino": ft.isoformat() if ft else "",
        })

    return {"results": results}