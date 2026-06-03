# web/app/blueprints/acuerdos_pago/routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash, send_file, make_response, send_file
from flask_login import login_required, current_user

from pathlib import Path
import os

from sqlalchemy import or_
from pathlib import Path

from app.extensions import db
from app.models import AcuerdoPago, TipoAcuerdoPago, Trabajador, Contrato, Obra, Empleador
from app.services.acuerdos_pago_docs import (
    TIPO_ACUERDO_LABELS,
    MODALIDAD_ACUERDO_LABELS,
    validar_acuerdo_pago,
    generar_docx_y_pdf_acuerdo_pago,
)

from . import bp

import re


def _to_int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "", "null") else None
    except Exception:
        return None


def _to_decimal(v: str | None) -> Decimal | None:
    if v is None:
        return None
    s = (v or "").strip().replace(".", "").replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _to_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


def _default_mes_inicio() -> str:
    hoy = date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"


def _tipo_enum_from_str(v: str | None) -> TipoAcuerdoPago | None:
    if not v:
        return None
    vv = v.strip().upper()
    try:
        return TipoAcuerdoPago[vv]
    except Exception:
        return None


@login_required
@bp.get("/")
def listado():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    tipo = (request.args.get("tipo") or "").strip().upper()

    query = AcuerdoPago.query

    # filtros
    if estado:
        query = query.filter(AcuerdoPago.estado == estado)

    if tipo:
        t = _tipo_enum_from_str(tipo)
        if t is not None:
            query = query.filter(AcuerdoPago.tipo == t)

    if q:
        # Búsqueda simple por nombre o rut (trabajador joined por lazy="joined")
        # Ojo: trabajador.rut está en tabla trabajadores; usamos ilike
        like = f"%{q}%"
        query = query.join(Trabajador, AcuerdoPago.trabajador_id == Trabajador.id).filter(
            or_(
                Trabajador.rut.ilike(like),
                Trabajador.nombres.ilike(like),
                Trabajador.ap_paterno.ilike(like),
                Trabajador.ap_materno.ilike(like),
                AcuerdoPago.concepto.ilike(like),
            )
        )

    acuerdos = query.order_by(AcuerdoPago.fecha_acuerdo.desc(), AcuerdoPago.id.desc()).limit(300).all()

    return render_template(
        "acuerdos_pago/acuerdos_pago_listado.html",
        acuerdos=acuerdos,
        q=q,
        estado=estado,
        tipo=tipo,
        tipo_labels=TIPO_ACUERDO_LABELS,
    )


@login_required
@bp.get("/nuevo")
def nuevo():
    # Form vacío
    acuerdo = AcuerdoPago(
        fecha_acuerdo=date.today(),
        modalidad="DESCUENTO_LIQUIDACION",
        cuotas=1,
        mes_inicio_descuento=_default_mes_inicio(),
        estado="BORRADOR",
    )

    return render_template(
        "acuerdos_pago/acuerdos_pago_form.html",
        acuerdo=acuerdo,
        modo="nuevo",
        tipo_enum=TipoAcuerdoPago,
        tipo_labels=TIPO_ACUERDO_LABELS,
        modalidad_labels=MODALIDAD_ACUERDO_LABELS,
    )


@login_required
@bp.post("/nuevo")
def nuevo_post():
    acuerdo = AcuerdoPago()

    # --- parse ---
    acuerdo.trabajador_id = _to_int(request.form.get("trabajador_id"))
    acuerdo.contrato_id = _to_int(request.form.get("contrato_id"))
    acuerdo.empleador_id = _to_int(request.form.get("empleador_id"))
    acuerdo.obra_id = _to_int(request.form.get("obra_id"))

    acuerdo.fecha_acuerdo = _to_date(request.form.get("fecha_acuerdo")) or date.today()
    acuerdo.tipo = _tipo_enum_from_str(request.form.get("tipo")) or TipoAcuerdoPago.DINERO

    acuerdo.concepto = (request.form.get("concepto") or "").strip()
    acuerdo.observaciones = (request.form.get("observaciones") or "").strip() or None

    acuerdo.modalidad = "DESCUENTO_LIQUIDACION"
    acuerdo.cuotas = _to_int(request.form.get("cuotas")) or 1

    mt = _to_decimal(request.form.get("monto_total"))
    acuerdo.monto_total = mt if mt is not None else 0

    mc = _to_decimal(request.form.get("monto_cuota"))
    acuerdo.monto_cuota = mc if mc is not None else 0

    acuerdo.mes_inicio_descuento = (request.form.get("mes_inicio_descuento") or "").strip() or None

    # Meta (EPP voluntario)
    epp_vol = (request.form.get("epp_mejora_voluntaria") or "").strip().lower() in ("1", "true", "on", "si", "sí")
    acuerdo.meta = {"epp_mejora_voluntaria": epp_vol} if epp_vol else {}

    acuerdo.estado = "BORRADOR"
    acuerdo.creado_por_user_id = getattr(current_user, "id", None)

    # Enlazar empleador/obra por defecto desde trabajador si no vienen
    if acuerdo.trabajador_id and (not acuerdo.empleador_id or not acuerdo.obra_id):
        t = Trabajador.query.get(acuerdo.trabajador_id)
        if t:
            if not acuerdo.obra_id:
                acuerdo.obra_id = t.obra_id
            if not acuerdo.empleador_id and t.empleador_preferente:
                acuerdo.empleador_id = t.empleador_preferente.id

    # Si cambiaron trabajador y no informaron empleador/obra, sugerimos desde trabajador
    if acuerdo.trabajador_id and (not acuerdo.empleador_id or not acuerdo.obra_id):
        t = Trabajador.query.get(acuerdo.trabajador_id)
        if t:
            if not acuerdo.obra_id:
                acuerdo.obra_id = getattr(t, "obra_id", None)
            if not acuerdo.empleador_id and getattr(t, "empleador_preferente", None):
                acuerdo.empleador_id = t.empleador_preferente.id

    errs = validar_acuerdo_pago(acuerdo)
    if errs:
        for e in errs:
            flash(e, "danger")
        return render_template(
            "acuerdos_pago/acuerdos_pago_form.html",
            acuerdo=acuerdo,
            modo="nuevo",
            tipo_enum=TipoAcuerdoPago,
            tipo_labels=TIPO_ACUERDO_LABELS,
            modalidad_labels=MODALIDAD_ACUERDO_LABELS,
        )

    db.session.add(acuerdo)
    db.session.commit()

    flash(f"Acuerdo de Pago creado (N° {acuerdo.numero}).", "success")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))


@login_required
@bp.get("/<int:acuerdo_id>")
def detalle(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    return render_template(
        "acuerdos_pago/acuerdos_pago_detalle.html",
        acuerdo=acuerdo,
        tipo_labels=TIPO_ACUERDO_LABELS,
    )


@login_required
@bp.get("/<int:acuerdo_id>/editar")
def editar(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if acuerdo.estado in ("ANULADO", "PAGADO"):
        flash("No se puede editar un acuerdo ANULADO o PAGADO.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    return render_template(
        "acuerdos_pago/acuerdos_pago_form.html",
        acuerdo=acuerdo,
        modo="editar",
        tipo_enum=TipoAcuerdoPago,
        tipo_labels=TIPO_ACUERDO_LABELS,
        modalidad_labels=MODALIDAD_ACUERDO_LABELS,
    )


@login_required
@bp.post("/<int:acuerdo_id>/editar")
def editar_post(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if acuerdo.estado in ("ANULADO", "PAGADO"):
        flash("No se puede editar un acuerdo ANULADO o PAGADO.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    acuerdo.trabajador_id = _to_int(request.form.get("trabajador_id"))
    acuerdo.contrato_id = _to_int(request.form.get("contrato_id"))
    acuerdo.empleador_id = _to_int(request.form.get("empleador_id"))
    acuerdo.obra_id = _to_int(request.form.get("obra_id"))

    acuerdo.fecha_acuerdo = _to_date(request.form.get("fecha_acuerdo")) or acuerdo.fecha_acuerdo or date.today()
    acuerdo.tipo = _tipo_enum_from_str(request.form.get("tipo")) or acuerdo.tipo

    acuerdo.concepto = (request.form.get("concepto") or "").strip()
    acuerdo.observaciones = (request.form.get("observaciones") or "").strip() or None

    acuerdo.cuotas = _to_int(request.form.get("cuotas")) or 1

    mt_i = _to_clp_int(request.form.get("monto_total"))
    if mt_i is not None:
        acuerdo.monto_total = Decimal(mt_i)

    # cuota automática (no editable)
    cuotas = int(acuerdo.cuotas or 1)
    total_i = int(mt_i if mt_i is not None else int(Decimal(str(acuerdo.monto_total or 0))))
    acuerdo.monto_cuota = Decimal((total_i // cuotas) if cuotas > 0 else 0)

    acuerdo.mes_inicio_descuento = (request.form.get("mes_inicio_descuento") or "").strip() or None

    epp_vol = (request.form.get("epp_mejora_voluntaria") or "").strip().lower() in ("1", "true", "on", "si", "sí")
    meta = acuerdo.meta if isinstance(acuerdo.meta, dict) else {}
    if epp_vol:
        meta["epp_mejora_voluntaria"] = True
    else:
        meta.pop("epp_mejora_voluntaria", None)
    acuerdo.meta = meta

    errs = validar_acuerdo_pago(acuerdo)
    if errs:
        for e in errs:
            flash(e, "danger")
        return render_template(
            "acuerdos_pago/acuerdos_pago_form.html",
            acuerdo=acuerdo,
            modo="editar",
            tipo_enum=TipoAcuerdoPago,
            tipo_labels=TIPO_ACUERDO_LABELS,
            modalidad_labels=MODALIDAD_ACUERDO_LABELS,
        )

    db.session.commit()
    flash("Acuerdo de Pago actualizado.", "success")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))


@login_required
@bp.post("/<int:acuerdo_id>/anular")
def anular(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if acuerdo.estado == "ANULADO":
        flash("El acuerdo ya está ANULADO.", "info")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    acuerdo.estado = "ANULADO"
    db.session.commit()
    flash("Acuerdo ANULADO.", "warning")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))


@login_required
@bp.post("/<int:acuerdo_id>/reabrir")
def reabrir(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if acuerdo.estado != "ANULADO":
        flash("Solo se pueden reabrir acuerdos ANULADOS.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    acuerdo.estado = "BORRADOR"
    db.session.commit()
    flash("Acuerdo reabierto como BORRADOR.", "success")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))


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
        .order_by(Trabajador.ap_paterno.asc(), Trabajador.ap_materno.asc(), Trabajador.nombres.asc())
        .limit(20)
    )

    results = []
    for t in query.all():
        nombre = " ".join([x for x in [t.nombres, t.ap_paterno, t.ap_materno] if x]).strip()
        results.append({
            "id": t.id,
            "rut": getattr(t, "rut_completo", None) or "",
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
            # 1) Obra del trabajador
            suggest["obra_id"] = getattr(t, "obra_id", None)

            # 2) Empleador desde la obra
            if suggest["obra_id"]:
                o = Obra.query.get(suggest["obra_id"])
                if o and getattr(o, "empleador_id", None):
                    suggest["empleador_id"] = o.empleador_id

            # 3) Empleador preferente (si existe)
            if not suggest["empleador_id"]:
                try:
                    emp_pref = getattr(t, "empleador_preferente", None)
                    if emp_pref is not None and getattr(emp_pref, "id", None):
                        suggest["empleador_id"] = emp_pref.id
                except Exception:
                    pass

            # 4) Fallback: último contrato
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



def _rename_with_suffix(path_str: str, suffix: str) -> tuple[str, str]:
    """
    Renombra en el mismo directorio agregando sufijo al nombre (antes de la extensión).
    Retorna: (new_path_str, new_filename)
    """
    p = Path(path_str)
    if not p.exists():
        return (path_str, p.name)

    new_name = f"{p.stem} - {suffix}{p.suffix}"
    new_p = p.with_name(new_name)

    # Reemplazo atómico si existe
    try:
        if new_p.exists():
            new_p.unlink()
        p.replace(new_p)
    except Exception:
        # fallback: si replace falla, dejamos el original
        return (path_str, p.name)

    return (str(new_p), new_p.name)


@bp.post("/<int:acuerdo_id>/emitir")
@login_required
def emitir(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)

    if acuerdo.estado == "ANULADO":
        flash("No puedes emitir un acuerdo ANULADO.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    errs = validar_acuerdo_pago(acuerdo)
    if errs:
        for e in errs:
            flash(e, "danger")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    # ✅ definimos la próxima versión ANTES, para usarla en el nombre
    next_ver = (getattr(acuerdo, "emitido_version", 0) or 0) + 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"v{next_ver}-{stamp}"

    docx_tmp, docx_nombre, pdf_tmp, pdf_nombre, docx_guardado, pdf_guardado = generar_docx_y_pdf_acuerdo_pago(acuerdo)

    # ✅ renombramos tmp para evitar cache por nombre
    docx_tmp2, docx_nombre2 = _rename_with_suffix(docx_tmp, suffix)
    pdf_tmp2, pdf_nombre2 = _rename_with_suffix(pdf_tmp, suffix)

    # ✅ Descargas SIEMPRE desde /tmp con nombre único
    acuerdo.docx_ruta = docx_tmp2
    acuerdo.docx_nombre = docx_nombre2

    acuerdo.pdf_ruta = pdf_tmp2
    acuerdo.pdf_nombre = pdf_nombre2

    # Auditoría (opcional)
    meta = acuerdo.meta if isinstance(acuerdo.meta, dict) else {}
    if docx_guardado:
        meta["docx_guardado"] = docx_guardado
    if pdf_guardado:
        meta["pdf_guardado"] = pdf_guardado
    acuerdo.meta = meta

    acuerdo.estado = "EMITIDO"
    acuerdo.emitido_version = next_ver

    db.session.commit()

    flash(f"Acuerdo de Pago N° {acuerdo.numero} emitido (DOCX + PDF generado).", "success")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))


@bp.post("/<int:acuerdo_id>/regenerar")
@login_required
def regenerar(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)

    if acuerdo.estado in ("ANULADO", "PAGADO"):
        flash("No se puede regenerar un acuerdo ANULADO o PAGADO.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    errs = validar_acuerdo_pago(acuerdo)
    if errs:
        for e in errs:
            flash(e, "danger")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    next_ver = (getattr(acuerdo, "emitido_version", 0) or 0) + 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"v{next_ver}-{stamp}"

    docx_tmp, docx_nombre, pdf_tmp, pdf_nombre, docx_guardado, pdf_guardado = generar_docx_y_pdf_acuerdo_pago(acuerdo)

    docx_tmp2, docx_nombre2 = _rename_with_suffix(docx_tmp, suffix)
    pdf_tmp2, pdf_nombre2 = _rename_with_suffix(pdf_tmp, suffix)

    acuerdo.docx_ruta = docx_tmp2
    acuerdo.docx_nombre = docx_nombre2

    acuerdo.pdf_ruta = pdf_tmp2
    acuerdo.pdf_nombre = pdf_nombre2

    meta = acuerdo.meta if isinstance(acuerdo.meta, dict) else {}
    if docx_guardado:
        meta["docx_guardado"] = docx_guardado
    if pdf_guardado:
        meta["pdf_guardado"] = pdf_guardado
    acuerdo.meta = meta

    acuerdo.estado = "EMITIDO"
    acuerdo.emitido_version = next_ver

    db.session.commit()

    flash(f"Documentos regenerados para Acuerdo N° {acuerdo.numero}.", "success")
    return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))



@bp.get("/<int:acuerdo_id>/descargar-pdf")
@login_required
def descargar_pdf(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if not acuerdo.pdf_ruta:
        flash("Este acuerdo aún no tiene PDF generado.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    p = Path(acuerdo.pdf_ruta)
    if not p.exists():
        flash("No se encontró el PDF en la ruta registrada (archivo inexistente).", "danger")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    st = p.stat()
    resp = make_response(send_file(
        str(p),
        as_attachment=True,
        download_name=acuerdo.pdf_nombre or f"ACUERDO_PAGO_{acuerdo.numero}.pdf",
        conditional=False,
        etag=False,  # ✅ importante: desactiva ETag (a veces los proxies/navegadores se ponen creativos)
        last_modified=None,
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"

    # ✅ Telemetría
    resp.headers["X-Served-Path"] = str(p)
    resp.headers["X-Served-Mtime"] = str(int(st.st_mtime))
    resp.headers["X-Served-Size"] = str(int(st.st_size))
    return resp


@bp.get("/<int:acuerdo_id>/descargar-docx")
@login_required
def descargar_docx(acuerdo_id: int):
    acuerdo = AcuerdoPago.query.get_or_404(acuerdo_id)
    if not acuerdo.docx_ruta:
        flash("Este acuerdo aún no tiene DOCX generado.", "warning")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    p = Path(acuerdo.docx_ruta)
    if not p.exists():
        flash("No se encontró el DOCX en la ruta registrada (archivo inexistente).", "danger")
        return redirect(url_for("acuerdos_pago.detalle", acuerdo_id=acuerdo.id))

    st = p.stat()
    resp = make_response(send_file(
        str(p),
        as_attachment=True,
        download_name=acuerdo.docx_nombre or f"ACUERDO_PAGO_{acuerdo.numero}.docx",
        conditional=False,
        etag=False,
        last_modified=None,
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"

    # ✅ Telemetría
    resp.headers["X-Served-Path"] = str(p)
    resp.headers["X-Served-Mtime"] = str(int(st.st_mtime))
    resp.headers["X-Served-Size"] = str(int(st.st_size))
    return resp


def _to_clp_int(v: str | None) -> int | None:
    """
    CLP sin decimales. Acepta: 250000, 250.000, $250.000, 250000.00 (lo limpia)
    """
    if v is None:
        return None
    s = (v or "").strip()
    if not s:
        return None
    s = re.sub(r"[^0-9]", "", s)  # SOLO dígitos
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None