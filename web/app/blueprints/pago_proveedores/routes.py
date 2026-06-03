# web/app/blueprints/pago_proveedores/routes.py
from __future__ import annotations

import os
import uuid
from datetime import datetime, date
from zoneinfo import ZoneInfo
from decimal import Decimal
from sqlalchemy import func, cast
from sqlalchemy.dialects.postgresql import JSONB

from flask import (
    current_app, render_template, request, redirect, url_for, flash, send_file
)
from flask_login import login_required, current_user

from ...extensions import db
from ...auth.decorators import role_required
from ...models import Tercero, Banco  # asumiendo que existen así
from ...models import PagoProveedoresLote, PagoProveedoresItem

from ...services.bank_nominas import (
    TEMPLATE_PAGOS_PROV,
    build_xlsx_from_template,
    get_template_path,
)
from ...services.pago_proveedores_engine import (
    parse_input_xlsx,
    build_rows,
    rut_parts_from_plain,
)

from . import bp


def _tmp_dir() -> str:
    p = os.path.join(current_app.instance_path, "tmp", "pago_proveedores")
    os.makedirs(p, exist_ok=True)
    return p


def _out_dir() -> str:
    p = os.path.join(current_app.instance_path, "uploads", "pago_proveedores")
    os.makedirs(p, exist_ok=True)
    return p

def _parse_date_yyyy_mm_dd(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    lots = (
        PagoProveedoresLote.query
        .order_by(PagoProveedoresLote.creado_en.desc())
        .limit(200)
        .all()
    )
    return render_template("pago_proveedores/listado.html", lots=lots)


@bp.get("/importar")
@login_required
@role_required("ADMIN", "OPERADOR")
def importar():
    hoy = datetime.now()
    return render_template(
        "pago_proveedores/importar.html",
        default_anio=hoy.year,
        default_mes=hoy.month,
    )


from flask import session  # arriba

def _import_dir(token: str) -> str:
    p = os.path.join(_tmp_dir(), token)
    os.makedirs(p, exist_ok=True)
    return p

def _safe_rm_tree(path: str) -> None:
    import shutil
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


@bp.post("/importar")
@login_required
@role_required("ADMIN", "OPERADOR")
def importar_post():
    anio = int(request.form.get("anio") or 0)
    mes = int(request.form.get("mes") or 0)

    f = request.files.get("archivo")
    if not f or not f.filename:
        flash("Debes seleccionar un archivo Excel para importar.", "error")
        return redirect(url_for("pago_proveedores.importar"))

    if anio <= 0 or not (1 <= mes <= 12):
        flash("Período inválido (año/mes).", "error")
        return redirect(url_for("pago_proveedores.importar"))

    # token de importación (preview)
    token = uuid.uuid4().hex
    imp_dir = _import_dir(token)

    upload_name = f.filename
    upload_path = os.path.join(imp_dir, "upload.xlsx")
    f.save(upload_path)

    lineas, excl_parse = parse_input_xlsx(upload_path)
    if not lineas and excl_parse:
        flash("No se pudo procesar el archivo: revisa el formato.", "error")
        return render_template(
            "pago_proveedores/preview.html",
            token=token,
            resultados=[],
            excluidos=excl_parse,
            anio=anio,
            mes=mes,
            archivo_origen=upload_name,
        )

    # Pre-cargar terceros necesarios
    needed_keys = set()
    for ln in lineas:
        rut_num, dv = rut_parts_from_plain(ln.rut_tercero_plain)
        if rut_num and dv:
            needed_keys.add((rut_num, dv))

    terceros = (
        Tercero.query
        .filter(db.tuple_(Tercero.rut_num, Tercero.dv).in_(list(needed_keys)))
        .all()
    )
    terceros_by_rut = {(t.rut_num, (t.dv or "").upper()): t for t in terceros}

    eng = build_rows(lineas, terceros_by_rut)
    excl_total = excl_parse + eng.excluidos

    # Generar XLSX preview por pagador (sin BD)
    template_path = get_template_path(current_app.root_path, TEMPLATE_PAGOS_PROV)
    preview_files = []
    resultados = []

    for pagador, rows in eng.ok_by_pagador.items():
        wb = build_xlsx_from_template(
            template_path=template_path,
            template_kind="PAGOS_PROV",
            rows=rows,
            anio=anio,
            mes=mes,
            glosa=f"Pago proveedores - {pagador} - {mes:02d}/{anio}",
        )

        out_name = f"PREVIEW_{anio}-{mes:02d}_Pago_Proveedores_{pagador}.xlsx"
        out_path = os.path.join(imp_dir, out_name)
        wb.save(out_path)

        preview_files.append({"pagador": pagador, "archivo": out_name})

        total_monto = sum((float(r.monto_total) for r in rows), 0.0)
        resultados.append(
            {
                "pagador": pagador,
                "total_items": len(rows),
                "total_monto": total_monto,
                "archivo": out_name,
            }
        )

    # Guardar contexto del preview en session (no BD)
    session["pp_preview"] = {
        "token": token,
        "anio": anio,
        "mes": mes,
        "archivo_origen": upload_name,
        "preview_files": preview_files,
        "excluidos": excl_total,
        # guardamos un resumen; las filas se recalculan al confirmar (seguro)
    }

    return render_template(
        "pago_proveedores/preview.html",
        token=token,
        resultados=resultados,
        excluidos=excl_total,
        anio=anio,
        mes=mes,
        archivo_origen=upload_name,
    )



@bp.get("/<int:lote_id>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(lote_id: int):
    lote = PagoProveedoresLote.query.get_or_404(lote_id)
    items = (
        PagoProveedoresItem.query
        .filter(PagoProveedoresItem.lote_id == lote.id)
        .order_by(PagoProveedoresItem.nombre_beneficiario.asc(), PagoProveedoresItem.fila_orden.asc())
        .all()
    )
    return render_template("pago_proveedores/detalle.html", lote=lote, items=items)


@bp.get("/<int:lote_id>/descargar")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def descargar(lote_id: int):
    lote = PagoProveedoresLote.query.get_or_404(lote_id)
    if not lote.archivo_generado:
        flash("Este lote no tiene archivo generado asociado.", "error")
        return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))

    abs_path = os.path.join(current_app.instance_path, lote.archivo_generado)
    if not os.path.exists(abs_path):
        flash("Archivo no encontrado en disco (posible limpieza/traslado).", "error")
        return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))

    return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))


@bp.get("/preview/<token>/descargar/<path:filename>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def descargar_preview(token: str, filename: str):
    imp_dir = _import_dir(token)
    abs_path = os.path.join(imp_dir, filename)

    if not os.path.exists(abs_path):
        flash("Archivo preview no encontrado.", "error")
        return redirect(url_for("pago_proveedores.importar"))

    return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))


@bp.post("/preview/<token>/cancelar")
@login_required
@role_required("ADMIN", "OPERADOR")
def cancelar_preview(token: str):
    data = (session.get("pp_preview") or {})
    if data.get("token") == token:
        session.pop("pp_preview", None)

    _safe_rm_tree(os.path.join(_tmp_dir(), token))
    flash("Importación cancelada. No se guardó ningún registro.", "info")
    return redirect(url_for("pago_proveedores.importar"))


@bp.post("/preview/<token>/guardar")
@login_required
@role_required("ADMIN", "OPERADOR")
def guardar_preview(token: str):
    data = (session.get("pp_preview") or {})
    if data.get("token") != token:
        flash("No se encontró una sesión de importación válida (expirada o distinta).", "error")
        return redirect(url_for("pago_proveedores.importar"))

    anio = int(data.get("anio") or 0)
    mes = int(data.get("mes") or 0)
    archivo_origen = data.get("archivo_origen") or "upload.xlsx"
    excl_total = data.get("excluidos") or []

    imp_dir = _import_dir(token)
    upload_path = os.path.join(imp_dir, "upload.xlsx")
    if not os.path.exists(upload_path):
        flash("Archivo original no encontrado para confirmar guardado.", "error")
        return redirect(url_for("pago_proveedores.importar"))

    # Recalcular determinísticamente
    lineas, excl_parse = parse_input_xlsx(upload_path)
    needed_keys = set()
    for ln in lineas:
        rut_num, dv = rut_parts_from_plain(ln.rut_tercero_plain)
        if rut_num and dv:
            needed_keys.add((rut_num, dv))

    terceros = (
        Tercero.query
        .filter(db.tuple_(Tercero.rut_num, Tercero.dv).in_(list(needed_keys)))
        .all()
    )
    terceros_by_rut = {(t.rut_num, (t.dv or "").upper()): t for t in terceros}

    eng = build_rows(lineas, terceros_by_rut)
    excl_total = (excl_parse + eng.excluidos)

    template_path = get_template_path(current_app.root_path, TEMPLATE_PAGOS_PROV)
    out_base = _out_dir()

    resultados = []
    try:
        for pagador, rows in eng.ok_by_pagador.items():
            lote = PagoProveedoresLote(
                pagador=pagador,
                anio=anio,
                mes=mes,
                archivo_origen=archivo_origen,
                creado_por_id=getattr(current_user, "id", None),
                excluidos=excl_total,
                estado="ACTIVO",
            )
            db.session.add(lote)
            db.session.flush()

            total_monto = 0.0
            for r in rows:
                total_monto += float(r.monto_total)

                db.session.add(
                    PagoProveedoresItem(
                        lote_id=lote.id,
                        tercero_id=r.tercero_id,
                        rut_tercero=r.rut_tercero,
                        rut_beneficiario=r.rut_beneficiario,
                        nombre_beneficiario=r.nombre_beneficiario,
                        codigo_banco=r.codigo_banco,
                        cuenta_destino=r.cuenta_destino,
                        correo=r.email_beneficiario,
                        facturas=[{"nro": x["nro"], "monto": float(x["monto"])} for x in (r.facturas or [])],
                        monto_total=float(r.monto_total),
                        glosa=r.glosa,
                        fila_orden=r.fila_orden,
                    )
                )

            lote.total_items = len(rows)
            lote.total_monto = total_monto

            wb = build_xlsx_from_template(
                template_path=template_path,
                template_kind="PAGOS_PROV",
                rows=rows,
                anio=anio,
                mes=mes,
                glosa=f"Pago proveedores - {pagador} - {mes:02d}/{anio}",
            )

            out_name = f"{anio}-{mes:02d}_Pago_Proveedores_{pagador}_lote{lote.id}.xlsx"
            out_path = os.path.join(out_base, out_name)
            wb.save(out_path)
            lote.archivo_generado = os.path.relpath(out_path, current_app.instance_path)

            resultados.append({"pagador": pagador, "lote_id": lote.id})

        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Error guardando la importación. No se guardó nada.", "error")
        return redirect(url_for("pago_proveedores.importar"))

    # limpiar preview
    session.pop("pp_preview", None)
    _safe_rm_tree(os.path.join(_tmp_dir(), token))

    flash("Importación guardada con éxito ✅", "success")
    # si hay 1 solo lote, lo mandamos al detalle
    if len(resultados) == 1:
        return redirect(url_for("pago_proveedores.detalle", lote_id=resultados[0]["lote_id"]))
    return redirect(url_for("pago_proveedores.listado"))

@bp.post("/<int:lote_id>/anular")
@login_required
@role_required("ADMIN", "OPERADOR")
def anular(lote_id: int):
    lote = PagoProveedoresLote.query.get_or_404(lote_id)

    if (lote.estado or "").upper() == "ANULADO":
        flash("Este lote ya está anulado.", "info")
        return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))

    motivo = (request.form.get("motivo") or "").strip()
    if not motivo:
        motivo = "Anulado por corrección de importación"

    lote.estado = "ANULADO"
    lote.anulado_en = datetime.now(timezone.utc)
    lote.anulado_por_id = getattr(current_user, "id", None)
    lote.anulado_motivo = motivo

    db.session.commit()
    flash("Lote anulado ✅ (histórico conservado).", "success")
    return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))


@bp.get("/gerencia")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def gerencia():
    """
    Dashboard gerencial:
    - KPIs del período
    - Top proveedores
    - Serie diaria (por creado_en del lote)
    - Lotes recientes (filtrables)
    """

    # -------------------------
    # Filtros (GET)
    # -------------------------
    hoy = datetime.now().date()
    desde = _parse_date_yyyy_mm_dd(request.args.get("desde")) or hoy.replace(day=1)
    hasta = _parse_date_yyyy_mm_dd(request.args.get("hasta")) or hoy

    pagador = (request.args.get("pagador") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()  # ACTIVO/ANULADO/"" (todos)
    qprov = (request.args.get("qprov") or "").strip()

    # Para filtros por date con timestamptz: incluimos todo el día "hasta"
    desde_dt = datetime.combine(desde, datetime.min.time())
    hasta_dt = datetime.combine(hasta, datetime.max.time())

    # -------------------------
    # Base query Items + Lote
    # -------------------------
    base = (
        db.session.query(PagoProveedoresItem, PagoProveedoresLote)
        .join(PagoProveedoresLote, PagoProveedoresItem.lote_id == PagoProveedoresLote.id)
        .filter(PagoProveedoresLote.creado_en >= desde_dt)
        .filter(PagoProveedoresLote.creado_en <= hasta_dt)
    )

    if pagador:
        base = base.filter(PagoProveedoresLote.pagador == pagador)

    if estado in {"ACTIVO", "ANULADO"}:
        base = base.filter(PagoProveedoresLote.estado == estado)

    if qprov:
        like = f"%{qprov.lower()}%"
        base = base.filter(
            func.lower(PagoProveedoresItem.nombre_beneficiario).like(like)
            | func.lower(PagoProveedoresItem.rut_tercero).like(like)
        )

    # -------------------------
    # KPI: totales (ACTIVO vs ANULADO)
    # -------------------------
    # Total activo (monto pagable)
    kpi_activo = (
        base.filter(PagoProveedoresLote.estado != "ANULADO")
        .with_entities(
            func.coalesce(func.sum(PagoProveedoresItem.monto_total), 0),
            func.count(func.distinct(PagoProveedoresLote.id)),
            func.count(func.distinct(PagoProveedoresItem.rut_tercero)),
            func.count(PagoProveedoresItem.id),
        )
        .first()
    )

    total_activo = Decimal(str(kpi_activo[0] or 0))
    lotes_activos = int(kpi_activo[1] or 0)
    proveedores_unicos = int(kpi_activo[2] or 0)
    items_total = int(kpi_activo[3] or 0)

    # Total anulado (control)
    kpi_anulado = (
        base.filter(PagoProveedoresLote.estado == "ANULADO")
        .with_entities(
            func.coalesce(func.sum(PagoProveedoresItem.monto_total), 0),
            func.count(func.distinct(PagoProveedoresLote.id)),
        )
        .first()
    )
    total_anulado = Decimal(str(kpi_anulado[0] or 0))
    lotes_anulados = int(kpi_anulado[1] or 0)

    pct_anulado = Decimal("0")
    if (total_activo + total_anulado) > 0:
        pct_anulado = (total_anulado / (total_activo + total_anulado)) * Decimal("100")

    promedio_por_proveedor = Decimal("0")
    if proveedores_unicos > 0:
        promedio_por_proveedor = total_activo / Decimal(str(proveedores_unicos))

    # -------------------------
    # Top proveedores (por monto)
    # + total de facturas aproximado = SUM(jsonb_array_length(facturas))
    # -------------------------
    fact_count_expr = func.coalesce(func.jsonb_array_length(cast(PagoProveedoresItem.facturas, JSONB)), 0)

    top_proveedores = (
        base.filter(PagoProveedoresLote.estado != "ANULADO")
        .with_entities(
            PagoProveedoresItem.rut_tercero.label("rut"),
            PagoProveedoresItem.nombre_beneficiario.label("nombre"),
            func.coalesce(func.sum(PagoProveedoresItem.monto_total), 0).label("monto"),
            func.count(PagoProveedoresItem.id).label("filas"),
            func.coalesce(func.sum(fact_count_expr), 0).label("facturas"),
        )
        .group_by(PagoProveedoresItem.rut_tercero, PagoProveedoresItem.nombre_beneficiario)
        .order_by(func.sum(PagoProveedoresItem.monto_total).desc())
        .limit(10)
        .all()
    )

    # -------------------------
    # Serie por día (monto total activo por fecha de creación del lote)
    # -------------------------
    serie_dia = (
        base.filter(PagoProveedoresLote.estado != "ANULADO")
        .with_entities(
            func.date(PagoProveedoresLote.creado_en).label("dia"),
            func.coalesce(func.sum(PagoProveedoresItem.monto_total), 0).label("monto"),
            func.count(func.distinct(PagoProveedoresLote.id)).label("lotes"),
        )
        .group_by(func.date(PagoProveedoresLote.creado_en))
        .order_by(func.date(PagoProveedoresLote.creado_en).asc())
        .all()
    )

    # -------------------------
    # Lotes recientes (para drill-down)
    # -------------------------
    lotes = (
        PagoProveedoresLote.query
        .filter(PagoProveedoresLote.creado_en >= desde_dt)
        .filter(PagoProveedoresLote.creado_en <= hasta_dt)
    )

    if pagador:
        lotes = lotes.filter(PagoProveedoresLote.pagador == pagador)
    if estado in {"ACTIVO", "ANULADO"}:
        lotes = lotes.filter(PagoProveedoresLote.estado == estado)

    lotes = lotes.order_by(PagoProveedoresLote.creado_en.desc()).limit(200).all()

    # -------------------------
    # Select pagadores para filtro
    # -------------------------
    pagadores = (
        db.session.query(PagoProveedoresLote.pagador)
        .distinct()
        .order_by(PagoProveedoresLote.pagador.asc())
        .all()
    )
    pagadores = [p[0] for p in pagadores if p and p[0]]

    return render_template(
        "pago_proveedores/gerencia.html",
        desde=desde,
        hasta=hasta,
        pagador=pagador,
        estado=estado,
        qprov=qprov,
        pagadores=pagadores,
        kpis={
            "total_activo": total_activo,
            "total_anulado": total_anulado,
            "pct_anulado": pct_anulado,
            "lotes_activos": lotes_activos,
            "lotes_anulados": lotes_anulados,
            "proveedores_unicos": proveedores_unicos,
            "items_total": items_total,
            "promedio_por_proveedor": promedio_por_proveedor,
        },
        top_proveedores=top_proveedores,
        serie_dia=serie_dia,
        lotes=lotes,
    )



@bp.post("/<int:lote_id>/pago")
@login_required
@role_required("ADMIN", "OPERADOR")
def set_pago(lote_id: int):
    lote = PagoProveedoresLote.query.get_or_404(lote_id)

    if (lote.estado or "ACTIVO") == "ANULADO":
        flash("No puedes cambiar estado de pago de un lote ANULADO.", "error")
        return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))

    estado_pago = (request.form.get("estado_pago") or "").strip().upper()
    if estado_pago not in {"PENDIENTE", "PAGADO"}:
        estado_pago = "PENDIENTE"

    fecha_pago_raw = (request.form.get("fecha_pago") or "").strip()
    obs_pago = (request.form.get("obs_pago") or "").strip()

    # parse fecha_pago
    fecha_pago = None
    if fecha_pago_raw:
        try:
            fecha_pago = datetime.strptime(fecha_pago_raw, "%Y-%m-%d").date()
        except Exception:
            fecha_pago = None

    lote.estado_pago = estado_pago
    lote.fecha_pago = fecha_pago
    lote.obs_pago = obs_pago[:400] if obs_pago else None

    if estado_pago == "PAGADO":
        lote.pagado_en = datetime.utcnow()
        lote.pagado_por_id = getattr(current_user, "id", None)
        # si no mandan fecha_pago, usamos hoy (recomendación práctica)
        if lote.fecha_pago is None:
            lote.fecha_pago = date.today()
    else:
        # volver a pendiente: mantenemos obs/fecha si quieres, o limpiamos (yo limpiaría auditoría de pagado)
        lote.pagado_en = None
        lote.pagado_por_id = None

    db.session.commit()
    flash(f"Estado de pago actualizado: {lote.estado_pago} ✅", "success")
    return redirect(url_for("pago_proveedores.detalle", lote_id=lote.id))
