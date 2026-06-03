# web/app/blueprints/egresos/routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa

from sqlalchemy import func, text, or_

from flask import (
    render_template, request, redirect, url_for, flash,
    send_file, abort
)
from flask_login import login_required, current_user

from ...extensions import db
from ...models import Egreso, EgresoItem, Trabajador, Contrato, Empleador, Obra
from ...services.egresos_docs import generar_docx_y_pdf_egreso

from . import bp


def _to_int(v: str | None) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _to_date(v: str | None) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


def _to_decimal(v: str | None) -> Decimal:
    if not v:
        return Decimal("0")
    v = v.replace(".", "").replace(",", ".").strip()
    try:
        return Decimal(v)
    except Exception:
        return Decimal("0")


def _build_items_from_form() -> list[tuple[int, str, Decimal]]:
    items: list[tuple[int, str, Decimal]] = []
    for i in range(1, 6):
        item_txt = (request.form.get(f"item_{i}") or "").strip()
        monto = _to_decimal(request.form.get(f"monto_{i}"))
        # Permitimos líneas vacías; se guardan como 0 si no hay item/monto
        if item_txt or monto != 0:
            items.append((i, item_txt, monto))
    return items


@bp.get("/")
@login_required
def listado():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    desde = _to_date(request.args.get("desde"))
    hasta = _to_date(request.args.get("hasta"))

    query = Egreso.query

    if estado in {"BORRADOR", "EMITIDO", "ANULADO"}:
        query = query.filter(Egreso.estado == estado)

    if desde:
        query = query.filter(Egreso.fecha_egreso >= desde)
    if hasta:
        query = query.filter(Egreso.fecha_egreso <= hasta)

    if q:
        # búsqueda simple: por número, motivo, externo, rut trabajador
        if q.isdigit():
            query = query.filter(Egreso.numero == int(q))
        else:
            like = f"%{q}%"
            query = query.filter(
                db.or_(
                    Egreso.motivo.ilike(like),
                    Egreso.pagado_a_nombre.ilike(like),
                    Egreso.pagado_a_rut.ilike(like),
                )
            )

    egresos = query.order_by(Egreso.id.desc()).limit(200).all()

    return render_template(
        "egresos/egresos_listado.html",
        egresos=egresos,
        q=q,
        estado=estado,
        desde=desde.isoformat() if desde else "",
        hasta=hasta.isoformat() if hasta else "",
    )


@bp.get("/nuevo")
@login_required
def nuevo():
    egreso = Egreso(
        fecha_egreso=date.today(),
        estado="BORRADOR",
        motivo="",
    )
    # Importante: número lo asigna la secuencia al insertar en DB
    return render_template("egresos/egreso_form.html", egreso=egreso, modo="nuevo")


@bp.post("/crear")
@login_required
def crear():
    modo_benef = (request.form.get("modo_beneficiario") or "TRABAJADOR").strip().upper()

    fecha_egreso = _to_date(request.form.get("fecha_egreso")) or date.today()
    motivo = (request.form.get("motivo") or "").strip()
    solicitante = (request.form.get("solicitante") or "").strip()
    solicitante_cargo = (request.form.get("solicitante_cargo") or "").strip()
    observaciones = (request.form.get("observaciones") or "").strip()

    if not motivo:
        flash("Debes indicar el motivo del egreso.", "warning")
        return redirect(url_for("egresos.nuevo"))

    egreso = Egreso(
        fecha_egreso=fecha_egreso,
        estado="BORRADOR",
        motivo=motivo,
        solicitante=solicitante or None,
        solicitante_cargo=solicitante_cargo or None,
        observaciones=observaciones or None,
        creado_por_user_id=getattr(current_user, "id", None),
    )

    if modo_benef == "EXTERNO":
        egreso.pagado_a_nombre = (request.form.get("pagado_a_nombre") or "").strip() or None
        egreso.pagado_a_rut = (request.form.get("pagado_a_rut") or "").strip() or None

        # Empleador/obra opcional para contexto (si el usuario lo selecciona)
        egreso.empleador_id = _to_int(request.form.get("empleador_id"))
        egreso.obra_id = _to_int(request.form.get("obra_id"))

        # contrato/trabajador quedan NULL
        egreso.trabajador_id = None
        egreso.contrato_id = None

    else:
        # TRABAJADOR
        trabajador_id = _to_int(request.form.get("trabajador_id"))
        contrato_id = _to_int(request.form.get("contrato_id"))

        if not trabajador_id:
            flash("Debes seleccionar un trabajador.", "warning")
            return redirect(url_for("egresos.nuevo"))

        egreso.trabajador_id = trabajador_id
        egreso.contrato_id = contrato_id

        # Empleador/obra: si viene contrato, lo fijamos desde contrato; si no, se pueden setear manual.
        if contrato_id:
            c = Contrato.query.get(contrato_id)
            if c:
                egreso.empleador_id = c.empleador_id
                egreso.obra_id = c.obra_id
        else:
            egreso.empleador_id = _to_int(request.form.get("empleador_id"))
            egreso.obra_id = _to_int(request.form.get("obra_id"))

    # ✅ Si SQLAlchemy manda numero=None, el DEFAULT de Postgres NO se ejecuta.
    # Forzamos el número desde la secuencia.
    if getattr(egreso, "numero", None) is None:
        egreso.numero = db.session.execute(text("SELECT nextval('egresos_numero_seq')")).scalar()

    db.session.add(egreso)
    db.session.flush()  # para obtener egreso.id y egreso.numero

    # Items
    for (orden, item_txt, monto) in _build_items_from_form():
        db.session.add(EgresoItem(
            egreso_id=egreso.id,
            orden=orden,
            item=item_txt or None,
            monto=monto,
        ))

    db.session.commit()
    flash(f"Egreso N° {egreso.numero} creado.", "success")
    return redirect(url_for("egresos.detalle", egreso_id=egreso.id))



@bp.get("/<int:egreso_id>")
@login_required
def detalle(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)

    total_items = sum((it.monto or Decimal("0")) for it in (egreso.items or []))

    return render_template(
        "egresos/egreso_detalle.html",
        egreso=egreso,
        total_items=total_items,
    )


@bp.get("/<int:egreso_id>/editar")
@login_required
def editar(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)
    return render_template("egresos/egreso_form.html", egreso=egreso, modo="editar")


@bp.post("/<int:egreso_id>/guardar")
@login_required
def guardar(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)

    if egreso.estado == "ANULADO":
        flash("No puedes editar un egreso ANULADO.", "warning")
        return redirect(url_for("egresos.detalle", egreso_id=egreso.id))

    modo_benef = (request.form.get("modo_beneficiario") or "TRABAJADOR").strip().upper()

    egreso.fecha_egreso = _to_date(request.form.get("fecha_egreso")) or egreso.fecha_egreso
    egreso.motivo = (request.form.get("motivo") or "").strip() or egreso.motivo
    egreso.solicitante = (request.form.get("solicitante") or "").strip() or None
    egreso.solicitante_cargo = (request.form.get("solicitante_cargo") or "").strip() or None
    egreso.observaciones = (request.form.get("observaciones") or "").strip() or None

    if modo_benef == "EXTERNO":
        egreso.pagado_a_nombre = (request.form.get("pagado_a_nombre") or "").strip() or None
        egreso.pagado_a_rut = (request.form.get("pagado_a_rut") or "").strip() or None
        egreso.trabajador_id = None
        egreso.contrato_id = None
        egreso.empleador_id = _to_int(request.form.get("empleador_id"))
        egreso.obra_id = _to_int(request.form.get("obra_id"))
    else:
        egreso.pagado_a_nombre = None
        egreso.pagado_a_rut = None
        egreso.trabajador_id = _to_int(request.form.get("trabajador_id"))
        egreso.contrato_id = _to_int(request.form.get("contrato_id"))
        contrato_id = egreso.contrato_id
        if contrato_id:
            c = Contrato.query.get(contrato_id)
            if c:
                egreso.empleador_id = c.empleador_id
                egreso.obra_id = c.obra_id
        else:
            egreso.empleador_id = _to_int(request.form.get("empleador_id"))
            egreso.obra_id = _to_int(request.form.get("obra_id"))

    # Rehacer items (simple y robusto)
    EgresoItem.query.filter(EgresoItem.egreso_id == egreso.id).delete()
    for (orden, item_txt, monto) in _build_items_from_form():
        db.session.add(EgresoItem(
            egreso_id=egreso.id,
            orden=orden,
            item=item_txt or None,
            monto=monto,
        ))

    db.session.commit()
    flash("Egreso actualizado.", "success")
    return redirect(url_for("egresos.detalle", egreso_id=egreso.id))

def _norm(s: str) -> str:
    return "".join((s or "").lower().split())



@bp.get("/api/trabajadores")
@login_required
def api_trabajadores():
    """
    Autocomplete: busca por nombre/apellidos/RUT.
    Devuelve los primeros 20 resultados.
    """
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return {"results": []}

    like = f"%{q}%"

    query = (
        Trabajador.query
        .filter(
            or_(
                Trabajador.rut.ilike(like),
                Trabajador.nombres.ilike(like),
                Trabajador.ap_paterno.ilike(like),
                Trabajador.ap_materno.ilike(like),
            )
        )
        .order_by(
            Trabajador.ap_paterno.asc(),
            Trabajador.ap_materno.asc(),
            Trabajador.nombres.asc(),
        )
        .limit(20)
    )

    results = []
    for t in query.all():
        nombre = " ".join([x for x in [t.nombres, t.ap_paterno, t.ap_materno] if x]).strip()
        results.append({
            "id": t.id,
            "rut": getattr(t, "rut_completo", "") or "",
            "nombre": nombre,
            "obra_id": getattr(t, "obra_id", None),
            "empleador_id": getattr(t, "empleador_id", None),
        })

    return {"results": results}


@bp.get("/api/contexto")
@login_required
def api_contexto():
    """
    Entrega combos para selects de empleadores y obras.
    Si viene trabajador_id, retorna además un 'suggest' con empleador_id/obra_id (si existe).
    """
    trabajador_id = _to_int(request.args.get("trabajador_id"))

    empleadores = (
        Empleador.query
        .order_by(Empleador.razon_social.asc())
        .all()
    )

    obras = (
        Obra.query
        .order_by(Obra.codigo.asc(), Obra.nombre.asc())
        .all()
    )

    suggest = {"empleador_id": None, "obra_id": None}

    if trabajador_id:
        t = Trabajador.query.get(trabajador_id)
        if t:
            # 1) Obra del trabajador (siempre)
            suggest["obra_id"] = getattr(t, "obra_id", None)

            # 2) Empleador desde la obra (si está configurado)
            if suggest["obra_id"]:
                o = Obra.query.get(suggest["obra_id"])
                if o and getattr(o, "empleador_id", None):
                    suggest["empleador_id"] = o.empleador_id

            # 3) Si aún no hay empleador, usar empleador_preferente (por contratos)
            if not suggest["empleador_id"]:
                try:
                    emp_pref = getattr(t, "empleador_preferente", None)
                    if emp_pref is not None and getattr(emp_pref, "id", None):
                        suggest["empleador_id"] = emp_pref.id
                except Exception:
                    pass

            # 4) Fallback final: último contrato con empleador (por si acaso)
            if not suggest["empleador_id"]:
                c = (
                    Contrato.query
                    .filter(Contrato.trabajador_id == t.id)
                    .filter(Contrato.empleador_id.isnot(None))
                    .order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc())
                    .first()
                )
                if c:
                    suggest["empleador_id"] = c.empleador_id

    return {
        "empleadores": [{"id": e.id, "label": e.razon_social} for e in empleadores],
        "obras": [{"id": o.id, "label": f"{o.codigo} · {o.nombre}", "empleador_id": o.empleador_id} for o in obras],
        "suggest": suggest,
    }


@bp.post("/<int:egreso_id>/emitir")
@login_required
def emitir(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)

    if egreso.estado == "ANULADO":
        flash("No puedes emitir un egreso ANULADO.", "warning")
        return redirect(url_for("egresos.detalle", egreso_id=egreso.id))

    # Generar DOCX + PDF desde plantilla
    docx_path, docx_nombre, pdf_path, pdf_nombre, docx_guardado, pdf_guardado = generar_docx_y_pdf_egreso(egreso)

    egreso.docx_nombre = docx_nombre
    egreso.docx_ruta = docx_path

    egreso.pdf_nombre = pdf_nombre
    egreso.pdf_ruta = pdf_path  # ruta local (para descargar)
    # Si quieres, podríamos guardar también docx_guardado/pdf_guardado en meta o campos nuevos.

    egreso.estado = "EMITIDO"
    db.session.commit()
    flash(f"Egreso N° {egreso.numero} emitido (DOCX + PDF generado).", "success")
    return redirect(url_for("egresos.detalle", egreso_id=egreso.id))


@bp.get("/<int:egreso_id>/descargar-docx")
@login_required
def descargar_docx(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)
    if not egreso.docx_ruta:
        flash("Este egreso aún no tiene DOCX generado.", "warning")
        return redirect(url_for("egresos.detalle", egreso_id=egreso.id))

    return send_file(
        egreso.docx_ruta,
        as_attachment=True,
        download_name=egreso.docx_nombre or f"EGRESO_{egreso.numero}.docx",
    )

@bp.get("/<int:egreso_id>/descargar-pdf")
@login_required
def descargar_pdf(egreso_id: int):
    egreso = Egreso.query.get_or_404(egreso_id)
    if not egreso.pdf_ruta:
        flash("Este egreso aún no tiene PDF generado.", "warning")
        return redirect(url_for("egresos.detalle", egreso_id=egreso.id))

    return send_file(
        egreso.pdf_ruta,
        as_attachment=True,
        download_name=egreso.pdf_nombre or f"EGRESO_{egreso.numero}.pdf",
    )