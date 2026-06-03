# web/app/blueprints/sueldos/routes.py
from __future__ import annotations

from datetime import datetime
from typing import Optional
import os
import uuid
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, make_response
from flask_login import login_required, current_user
from sqlalchemy import func, literal, case, and_
from werkzeug.utils import secure_filename
from jinja2 import TemplateError
from decimal import Decimal


from ...extensions import db
from ...auth.decorators import role_required
from ...models import (
    SueldoNomina,
    SueldoDetalle,
    Obra,
    Trabajador,
    Empleador,
    SolicitudFondos,
    SolicitudFondosItem,
)

from ...services.import_sueldos import import_sueldos_from_excel

bp = Blueprint("sueldos", __name__, url_prefix="/sueldos")


# ---------------------------
# Helpers
# ---------------------------
def _to_int(v: str | None) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() else None
    except Exception:
        return None


def _upper(v: str | None) -> str:
    return (v or "").strip().upper()


def _allowed_obras_for_user_ids() -> set[int]:
    if current_user.has_role("ADMIN"):
        return set()
    return {o.id for o in (current_user.obras or [])}


def _require_obra_access(obra_id: int) -> None:
    if current_user.has_role("ADMIN"):
        return
    allowed = _allowed_obras_for_user_ids()
    if not allowed or obra_id not in allowed:
        abort(403)


def _require_nomina_access(n: SueldoNomina) -> None:
    # scope por centro_costo derivado de obras asignadas
    if current_user.has_role("ADMIN"):
        return

    allowed_obras = _allowed_obras_for_user_ids()
    if not allowed_obras:
        abort(403)

    allowed_cc = {
        str(cc or "").strip().upper()
        for (cc,) in (
            db.session.query(func.coalesce(Obra.centro_costo, ""))
            .filter(Obra.id.in_(sorted(allowed_obras)))
            .distinct()
            .all()
        )
        if str(cc or "").strip()
    }

    cc = (n.centro_costo or "").strip().upper()
    if not cc or cc not in allowed_cc:
        abort(403)


def _tmp_upload_dir() -> str:
    d = os.path.join(current_app.instance_path, "tmp_uploads")
    os.makedirs(d, exist_ok=True)
    return d


def _allowed_ext(filename: str) -> bool:
    fn = (filename or "").lower()
    return fn.endswith(".xlsx") or fn.endswith(".xls")

def _tipo_key_expr_sueldos():
    return func.upper(func.trim(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO")))

def _tipo_priority_expr_sueldos(tipo_key_expr):
    # 0 = JEFATURA U OTROS, 1 = DIRECTO, 2 = resto
    return case(
        (tipo_key_expr == "JEFATURA U OTROS", 0),
        (tipo_key_expr == "DIRECTO", 1),
        else_=2,
    )

def _tipo_key_expr():
    return func.upper(func.trim(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO")))

def _tipo_priority_expr(tipo_key_expr):
    # 0 = JEFATURA U OTROS, 1 = DIRECTO, 2 = resto
    return case(
        (tipo_key_expr == "JEFATURA U OTROS", 0),
        (tipo_key_expr == "DIRECTO", 1),
        else_=2,
    )


# ---------------------------
# Importar (UPLOAD)
# ---------------------------
@bp.route("/importar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def importar():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Debes seleccionar un archivo.", "warning")
            return redirect(url_for("sueldos.importar"))

        if not _allowed_ext(f.filename):
            flash("Formato no permitido. Sube un archivo .xlsx (recomendado).", "warning")
            return redirect(url_for("sueldos.importar"))

        anio = _to_int(request.form.get("anio")) or 0
        mes = _to_int(request.form.get("mes")) or 0
        empleador_id = _to_int(request.form.get("empleador_id")) or 0
        obra_id = _to_int(request.form.get("obra_id")) or 0
        allow_reimport = (request.form.get("allow_reimport") == "1")

        # Validaciones duras
        if anio < 2000 or anio > 2100:
            flash("Año inválido.", "warning")
            return redirect(url_for("sueldos.importar"))

        if mes < 1 or mes > 12:
            flash("Mes inválido. Debe estar entre 1 y 12.", "warning")
            return redirect(url_for("sueldos.importar"))

        if not empleador_id or not obra_id:
            flash("Completa Obra y Empleador (además de Año/Mes).", "error")
            return redirect(url_for("sueldos.importar"))

        # Control de acceso por obra
        _require_obra_access(obra_id)

        obra = Obra.query.get(obra_id)
        if not obra:
            flash("Obra no encontrada.", "warning")
            return redirect(url_for("sueldos.importar"))

        cc = _upper(getattr(obra, "centro_costo", None))
        if not cc:
            flash("La obra seleccionada no tiene Centro de Costo configurado.", "error")
            return redirect(url_for("sueldos.importar"))

        # Guardar temporal
        token = uuid.uuid4().hex
        safe_name = secure_filename(f.filename)
        filename = f"{token}_{safe_name}"
        tmp_path = os.path.join(_tmp_upload_dir(), filename)

        f.save(tmp_path)

        try:
            res = import_sueldos_from_excel(
                filepath=tmp_path,
                anio=anio,
                mes=mes,
                centro_costo=cc,
                empleador_id=empleador_id,
                obra_id=obra_id,
                user_id=current_user.id,
                allow_reimport=allow_reimport,
            )

            flash(
                f"Importación OK. Nómina #{res.get('nomina_id')} ({res.get('periodo')} · CC {res.get('centro_costo')}).",
                "success",
            )
            return redirect(url_for("sueldos.detalle", nomina_id=res["nomina_id"]))

        except Exception as e:
            flash(f"Error importando sueldos: {e}", "error")
            return redirect(url_for("sueldos.importar"))

        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    # GET
    now = datetime.now()

    q_obras = Obra.query
    if not current_user.has_role("ADMIN"):
        allowed = _allowed_obras_for_user_ids()
        if not allowed:
            obras = []
        else:
            q_obras = q_obras.filter(Obra.id.in_(sorted(allowed)))
            obras = q_obras.order_by(Obra.nombre.asc()).all()
    else:
        obras = q_obras.order_by(Obra.nombre.asc()).all()

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    return render_template(
        "sueldos/sueldos_importar.html",
        obras=obras,
        empleadores=empleadores,
        anio_default=now.year,
        mes_default=now.month,
    )


# ---------------------------
# Listado (ordenado por CC)
# ---------------------------
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    q_cc = _upper(request.args.get("centro_costo"))
    q_periodo = (request.args.get("periodo") or "").strip()  # YYYY-MM
    q_estado = _upper(request.args.get("estado"))
    q_empleador_id = _to_int(request.args.get("empleador_id"))

    q = SueldoNomina.query

    if not current_user.has_role("ADMIN"):
        allowed_obras = _allowed_obras_for_user_ids()
        if not allowed_obras:
            flash("No tienes obras asignadas. Solicita acceso a una obra para ver nóminas.", "warning")
            return render_template(
                "sueldos/sueldos_listado.html",
                nominas=[],
                centros=[],
                empleadores=[],
                q_cc=q_cc,
                q_periodo=q_periodo,
                q_estado=q_estado,
                q_empleador_id=q_empleador_id,
            )

        allowed_cc = {
            str(cc or "").strip().upper()
            for (cc,) in (
                db.session.query(func.coalesce(Obra.centro_costo, ""))
                .filter(Obra.id.in_(sorted(allowed_obras)))
                .distinct()
                .all()
            )
            if str(cc or "").strip()
        }
        q = q.filter(SueldoNomina.centro_costo.in_(sorted(allowed_cc))) if allowed_cc else q.filter(literal(False))

    if q_cc:
        q = q.filter(SueldoNomina.centro_costo == q_cc)

    if q_periodo:
        try:
            anio = int(q_periodo.split("-")[0])
            mes = int(q_periodo.split("-")[1])
            q = q.filter(SueldoNomina.anio == anio, SueldoNomina.mes == mes)
        except Exception:
            flash("Período inválido. Usa formato YYYY-MM (ej: 2026-01).", "warning")

    if q_estado:
        q = q.filter(SueldoNomina.estado == q_estado)

    if q_empleador_id:
        q = q.filter(SueldoNomina.empleador_id == q_empleador_id)

    nominas = (
        q.order_by(
            SueldoNomina.anio.desc(),
            SueldoNomina.mes.desc(),
            SueldoNomina.centro_costo.asc(),
            SueldoNomina.empleador_id.asc(),
            SueldoNomina.id.desc(),
        )
        .all()
    )

    centros_q = db.session.query(Obra.centro_costo).filter(Obra.centro_costo.isnot(None))
    if not current_user.has_role("ADMIN"):
        allowed_obras = _allowed_obras_for_user_ids()
        centros_q = centros_q.filter(Obra.id.in_(sorted(allowed_obras))) if allowed_obras else centros_q.filter(literal(False))
    centros = [r[0] for r in centros_q.distinct().order_by(Obra.centro_costo.asc()).all()]

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    return render_template(
        "sueldos/sueldos_listado.html",
        nominas=nominas,
        centros=centros,
        empleadores=empleadores,
        q_cc=q_cc,
        q_periodo=q_periodo,
        q_estado=q_estado,
        q_empleador_id=q_empleador_id,
    )


# ===========================
# Nóminas bancarias (SUELDOS)
# ===========================
# Nota técnica:
# - Antes se intentó usar save_virtual_workbook (openpyxl), pero en versiones nuevas
#   esa función ya no existe y rompe el arranque del worker.
# - Acá NO la necesitamos, porque exportamos guardando el workbook a disco (wb.save(filepath))
#   y luego descargamos con send_file.

from ...services.bank_nominas import (
    TEMPLATE_PAGOS_REMUN,
    TEMPLATE_TRANSFER_MAS,
    get_template_path,
    build_bank_rows,
    aggregate_rows,
    build_xlsx_from_template,
    glosa_sueldo,
)


def _tmp_bank_exports_dir() -> str:
    d = os.path.join(current_app.instance_path, "tmp_bank_exports")
    os.makedirs(d, exist_ok=True)
    return d



@bp.get("/nominas-banco")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def nominas_banco():
    # obras según permisos (misma lógica que importar/listado)
    q_obras = Obra.query
    if not current_user.has_role("ADMIN"):
        allowed = _allowed_obras_for_user_ids()
        if not allowed:
            obras = []
        else:
            obras = q_obras.filter(Obra.id.in_(sorted(allowed))).order_by(Obra.nombre.asc()).all()
    else:
        obras = q_obras.order_by(Obra.nombre.asc()).all()

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    # default_periodo: último mes VISADO (si no hay, último existente)
    ultimo = (
        db.session.query(SueldoNomina.anio, SueldoNomina.mes)
        .filter(SueldoNomina.estado == "VISADA")
        .order_by(SueldoNomina.anio.desc(), SueldoNomina.mes.desc())
        .first()
    )
    if not ultimo:
        ultimo = (
            db.session.query(SueldoNomina.anio, SueldoNomina.mes)
            .order_by(SueldoNomina.anio.desc(), SueldoNomina.mes.desc())
            .first()
        )

    default_periodo = f"{int(ultimo[0]):04d}-{int(ultimo[1]):02d}" if ultimo else ""

    form = {
        "plantilla": "PAGOS_REMUN",
        "periodo": default_periodo,
        "empresa_ids": [],
        "obra_ids": [],
    }

    return render_template(
        "sueldos/sueldos_nominas_banco.html",
        obras=obras,
        empleadores=empleadores,
        default_periodo=default_periodo,
        form=form,
        resultado=None,
    )


@bp.post("/nominas-banco/generar")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_generar():
    plantilla = (request.form.get("plantilla") or "").strip().upper()
    if plantilla not in {"PAGOS_REMUN", "TRANSFER_MAS"}:
        plantilla = "PAGOS_REMUN"

    periodo = (request.form.get("periodo") or "").strip()  # YYYY-MM
    try:
        anio = int(periodo.split("-")[0])
        mes = int(periodo.split("-")[1])
    except Exception:
        flash("Período inválido. Usa formato YYYY-MM.", "warning")
        return redirect(url_for("sueldos.nominas_banco"))

    empresa_ids = request.form.getlist("empresa_ids")
    obra_ids = request.form.getlist("obra_ids")

    empresa_ids_int = sorted([int(x) for x in empresa_ids if str(x).strip().isdigit()])
    obra_ids_int = sorted([int(x) for x in obra_ids if str(x).strip().isdigit()])

    # Obras según permisos (REVISOR incluido, pero generar solo ADMIN/OPERADOR ya está en decorator)
    allowed_obras = set()
    if not current_user.has_role("ADMIN"):
        allowed_obras = _allowed_obras_for_user_ids()
        if not allowed_obras:
            flash("No tienes obras asignadas para generar nóminas bancarias.", "warning")
            return redirect(url_for("sueldos.nominas_banco"))

    # Lista obras para UI (respetando permisos)
    q_obras_ui = Obra.query
    if not current_user.has_role("ADMIN"):
        q_obras_ui = q_obras_ui.filter(Obra.id.in_(sorted(allowed_obras)))
    obras_ui = q_obras_ui.order_by(Obra.nombre.asc()).all()

    empleadores_ui = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    # Base: traer detalles OK con liquido > 0, join a Nomina para filtrar por periodo y empleador
    q = (
        db.session.query(SueldoDetalle, Trabajador, literal(None))
        .join(SueldoNomina, SueldoNomina.id == SueldoDetalle.nomina_id)
        .outerjoin(Trabajador, Trabajador.id == SueldoDetalle.trabajador_id)
        .filter(SueldoNomina.anio == anio, SueldoNomina.mes == mes)
        .filter(SueldoDetalle.estado_linea == "OK")
        .filter(func.coalesce(SueldoDetalle.liquido, 0) > 0)
    )

    # filtro empleadores
    if empresa_ids_int:
        q = q.filter(SueldoNomina.empleador_id.in_(empresa_ids_int))

    # filtro obras: solo si seleccionan. Si no seleccionan, todas (según permisos)
    if obra_ids_int:
        # si no es admin, validar que obra_ids están dentro de allowed
        if not current_user.has_role("ADMIN"):
            if any(oid not in allowed_obras for oid in obra_ids_int):
                abort(403)
        q = q.filter(SueldoDetalle.obra_id.in_(obra_ids_int))
    else:
        if not current_user.has_role("ADMIN"):
            q = q.filter(SueldoDetalle.obra_id.in_(sorted(allowed_obras)))

    # ⚠️ Banco: en anticipos tú pasabas (detalle, trabajador, banco)
    # Aquí armamos "banco" desde trabajador.banco (o como se llame).
    # Ajusta el getattr si tu relación se llama diferente.
    rows_raw = q.all()

    detalles_rows = []
    obras_set = set()

    for det, t, _ in rows_raw:
        if det and getattr(det, "obra_id", None):
            obras_set.add(int(det.obra_id))
        banco = getattr(t, "banco", None) if t else None  # <- AJUSTAR si tu campo se llama distinto
        detalles_rows.append((det, t, banco))

    build = build_bank_rows(detalles_rows, amount_attr="liquido")
    ok_agg = aggregate_rows(build.ok_rows)

    total_monto = float(sum([r.monto for r in ok_agg], start=Decimal("0")))

    # Construcción XLSX
    template_filename = TEMPLATE_PAGOS_REMUN if plantilla == "PAGOS_REMUN" else TEMPLATE_TRANSFER_MAS
    template_path = get_template_path(current_app.root_path, template_filename)

    glosa = glosa_sueldo(anio, mes)

    wb = build_xlsx_from_template(
        template_path=template_path,
        template_kind=plantilla,
        rows=ok_agg,
        anio=anio,
        mes=mes,
        glosa=glosa,
        cuenta_origen_transfer_mas="5555555555",  # si quieres, lo hacemos configurable por Empleador
    )

    # Guardar para descarga por token
    token = uuid.uuid4().hex
    out_dir = _tmp_bank_exports_dir()

    # Nombre bonito
    if empresa_ids_int and len(empresa_ids_int) == 1:
        emp = Empleador.query.get(empresa_ids_int[0])
        emp_name = (emp.razon_social if emp else "Empresa").strip()
    elif empresa_ids_int:
        emp_name = "Varias empresas"
    else:
        emp_name = "Todas las empresas"

    safe_emp = re.sub(r"[^a-zA-Z0-9 _.-]+", "", emp_name).strip() or "Empresas"
    filename = f"{anio:04d}-{mes:02d} Sueldos - {safe_emp}.xlsx".replace("  ", " ")

    filepath = os.path.join(out_dir, f"{token}.xlsx")
    wb.save(filepath)

    resultado = {
        "periodo": f"{anio:04d}-{mes:02d}",
        "plantilla_label": "Pagos Masivos Remuneraciones Santander" if plantilla == "PAGOS_REMUN" else "Transferencias Masivas Santander",
        "empresas_label": emp_name,
        "download_token": token,
        "download_filename": filename,
        "ok_count": len(ok_agg),
        "excluidos_count": len(build.excluidos),
        "excluidos": build.excluidos,
        "total_monto": total_monto,
        "obras_count": len(obras_set),
    }

    form = {
        "plantilla": plantilla,
        "periodo": f"{anio:04d}-{mes:02d}",
        "empresa_ids": empresa_ids_int,
        "obra_ids": obra_ids_int,
    }

    return render_template(
        "sueldos/sueldos_nominas_banco.html",
        obras=obras_ui,
        empleadores=empleadores_ui,
        default_periodo=f"{anio:04d}-{mes:02d}",
        form=form,
        resultado=resultado,
    )


@bp.get("/nominas-banco/descargar/<token>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def nominas_banco_descargar(token: str):
    token = (token or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        abort(404)

    filepath = os.path.join(_tmp_bank_exports_dir(), f"{token}.xlsx")
    if not os.path.exists(filepath):
        abort(404)

    # nombre “genérico” si no llega desde UI; el browser igual descarga OK
    download_name = f"nomina_sueldos_{token}.xlsx"

    from flask import send_file
    return send_file(
        filepath,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_age=0,
        conditional=False,
    )


# ---------------------------
# Detalle (planilla editable)
# ---------------------------
@bp.get("/<int:nomina_id>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(nomina_id: int):
    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    q_text = (request.args.get("q") or "").strip()
    q_estado_linea = _upper(request.args.get("estado_linea"))

    q = (
        db.session.query(SueldoDetalle, Trabajador.ap_paterno, Trabajador.ap_materno, Trabajador.nombres)
        .outerjoin(Trabajador, Trabajador.id == SueldoDetalle.trabajador_id)
        .filter(SueldoDetalle.nomina_id == nomina.id)
    )

    if q_text:
        like = f"%{q_text}%"
        q = q.filter(
            (func.coalesce(SueldoDetalle.rut, "").ilike(like))
            | (func.coalesce(SueldoDetalle.nombre_completo, "").ilike(like))
            | (func.coalesce(SueldoDetalle.observacion, "").ilike(like))
            | (func.coalesce(Trabajador.ap_paterno, "").ilike(like))
            | (func.coalesce(Trabajador.ap_materno, "").ilike(like))
            | (func.coalesce(Trabajador.nombres, "").ilike(like))
        )

    if q_estado_linea:
        q = q.filter(SueldoDetalle.estado_linea == q_estado_linea)

    rows = (
        q.order_by(
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            func.coalesce(SueldoDetalle.nombre_completo, "").asc(),
        )
        .all()
    )

    detalles = []
    for d, ap_paterno, ap_materno, nombres in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres]
            if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        detalles.append({
            "d": d,
            "nombre_ordenado": nombre_ordenado,
        })

    total_anticipo = (
        db.session.query(func.coalesce(func.sum(SueldoDetalle.anticipo), 0))
        .filter(SueldoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    total_liquido = (
        db.session.query(func.coalesce(func.sum(SueldoDetalle.liquido), 0))
        .filter(SueldoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    total_alcance_liquido = (
        db.session.query(
            func.coalesce(func.sum(SueldoDetalle.anticipo + SueldoDetalle.liquido), 0)
        )
        .filter(SueldoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    # ==========================
    # Solicitudes de fondos disponibles (mismo CC)
    # ==========================
    cc = _upper(nomina.centro_costo)
    solicitudes_cc = []
    if cc:
        solicitudes_cc = (
            SolicitudFondos.query
            .filter(SolicitudFondos.centro_costo == cc)
            .filter(SolicitudFondos.estado.in_(["BORRADOR", "ENVIADA", "APROBADA"]))
            .order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.numero.desc())
            .all()
        )

    # ==========================
    # KPIs de integración (REMU) para la nómina
    # ==========================
    total_integrado = (
        db.session.query(func.coalesce(func.sum(SolicitudFondosItem.monto), 0))
        .filter(SolicitudFondosItem.sueldo_nomina_id == nomina.id)
        .scalar()
    )

    return render_template(
        "sueldos/sueldos_detalle.html",
        nomina=nomina,
        detalles=detalles,
        total_anticipo=total_anticipo,
        total_liquido=total_liquido,
        total_alcance_liquido=total_alcance_liquido,
        q_text=q_text,
        q_estado_linea=q_estado_linea,
        solicitudes_cc=solicitudes_cc,
        total_integrado=total_integrado,
    )


# ---------------------------
# Guardar planilla (liquido + observación)
# ---------------------------
@bp.post("/<int:nomina_id>/guardar")
@login_required
@role_required("ADMIN", "OPERADOR")
def guardar(nomina_id: int):
    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    if nomina.estado != "BORRADOR":
        flash("Solo se puede editar una nómina en estado BORRADOR.", "warning")
        return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))

    detalles_db = SueldoDetalle.query.filter_by(nomina_id=nomina.id).all()

    for d in detalles_db:
        key_l = f"liquido_{d.id}"
        key_o = f"obs_{d.id}"

        if key_l in request.form:
            raw = (request.form.get(key_l) or "").strip()
            raw = raw.replace("$", "").replace(" ", "").replace(".", "").replace(",", ".")
            try:
                liquido = float(raw) if raw else 0.0
            except Exception:
                liquido = 0.0
            d.liquido = liquido

        if key_o in request.form:
            d.observacion = (request.form.get(key_o) or "").strip() or None

    db.session.commit()
    flash("Planilla guardada correctamente.", "success")
    return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))


# ---------------------------
# Flujo (igual anticipos)
# ---------------------------
@bp.post("/<int:nomina_id>/enviar_visacion")
@login_required
@role_required("ADMIN", "OPERADOR")
def enviar_visacion(nomina_id: int):
    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    if nomina.estado != "BORRADOR":
        flash("Solo se puede enviar a visación una nómina en BORRADOR.", "warning")
        return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))

    nomina.estado = "ENVIADA_A_VISACION"
    db.session.commit()
    flash("Nómina enviada a visación.", "success")
    return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))


@bp.post("/<int:nomina_id>/visar")
@login_required
@role_required("ADMIN")
def visar(nomina_id: int):
    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    if nomina.estado not in {"ENVIADA_A_VISACION", "BORRADOR"}:
        flash("La nómina no está en un estado visable.", "warning")
        return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))

    nomina.estado = "VISADA"
    nomina.visado_por = current_user.id
    nomina.visado_en = datetime.utcnow()
    db.session.commit()
    flash("Nómina visada correctamente.", "success")
    return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))


@bp.post("/<int:nomina_id>/revertir_borrador")
@login_required
@role_required("ADMIN")
def revertir_borrador(nomina_id: int):
    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    if nomina.estado == "BORRADOR":
        flash("La nómina ya está en BORRADOR.", "info")
        return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))

    nomina.estado = "BORRADOR"
    db.session.commit()
    flash("Nómina revertida a BORRADOR. Edición habilitada.", "success")
    return redirect(url_for("sueldos.detalle", nomina_id=nomina.id))


# ---------------------------
# Integrar a Solicitud de Fondos (REMU) - POR CENTRO DE COSTO
# ---------------------------

@bp.post("/<int:nomina_id>/integrar-solicitud")
@login_required
@role_required("ADMIN", "OPERADOR")
def sueldos_integrar_solicitud(nomina_id: int):
    from sqlalchemy.exc import IntegrityError

    next_url = request.form.get("next") or url_for("sueldos.detalle", nomina_id=nomina_id)

    nomina = SueldoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    solicitud_id = _to_int(request.form.get("solicitud_id"))
    if not solicitud_id:
        flash("Debes seleccionar una Solicitud de Fondos.", "warning")
        return redirect(next_url)

    solicitud = SolicitudFondos.query.get_or_404(solicitud_id)

    # ✅ regla mandatoria: centro de costo
    if _upper(solicitud.centro_costo) != _upper(nomina.centro_costo):
        flash("La Solicitud de Fondos no corresponde al mismo Centro de Costo de la nómina.", "danger")
        return redirect(next_url)

    # ✅ Solo líneas OK con líquido > 0
    detalles = [
        d for d in (nomina.detalles or [])
        if (d.estado_linea == "OK") and (d.liquido is not None) and (float(d.liquido) > 0)
    ]

    if not detalles:
        flash("No hay líneas OK con líquido > 0 para integrar.", "info")
        return redirect(next_url)

    # ==========================================================
    # Etiquetas de integración
    # ==========================================================
    periodo_tag = f"{nomina.periodo_str} | {nomina.empleador.razon_social}".strip()
    descripcion_std = f"Sueldo líquido {nomina.periodo_str} · {nomina.empleador.razon_social}"

    # ==========================================================
    # 🧹 OPCIÓN: Limpiar REMU del período antes de reintegrar
    # ==========================================================
    wipe_remu = (request.form.get("wipe_remu") or "") == "1"
    borrados = 0

    if wipe_remu:
        # Opción conservadora: borrar SOLO SUELDOS provenientes de sueldos (no tocar otros REMU)
        q_del = (
            SolicitudFondosItem.query
            .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
            .filter(SolicitudFondosItem.seccion == "REMU")
            .filter(SolicitudFondosItem.concepto == "SUELDO")
            .filter(SolicitudFondosItem.control_interno == periodo_tag)
            .filter(
                (SolicitudFondosItem.sueldo_nomina_id.isnot(None)) |
                (SolicitudFondosItem.sueldo_detalle_id.isnot(None))
            )
        )

        borrados = q_del.delete(synchronize_session=False)
        # ✅ OJO: hacemos flush/commit después junto con integración (una sola transacción)
        # pero como ya borramos en sesión, seguimos.

    # ==========================================================
    # Cargar existentes REMU del período (para reemplazo premium)
    # (si wipe_remu=True, esto debería venir vacío)
    # ==========================================================
    existentes_periodo = (
        SolicitudFondosItem.query
        .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
        .filter(SolicitudFondosItem.seccion == "REMU")
        .filter(SolicitudFondosItem.concepto == "SUELDO")
        .filter(SolicitudFondosItem.control_interno == periodo_tag)
        .all()
    )

    idx_premium = {}
    for it in existentes_periodo:
        k = (int(it.trabajador_id or 0), int(it.contrato_id or 0), (it.control_interno or "").strip())
        if k[0] != 0:
            idx_premium[k] = it

    # ==========================================================
    # Index duro por sueldo_detalle_id (evita uq_sf_item_sueldo_detalle)
    # ==========================================================
    detalle_ids = [int(d.id) for d in detalles if getattr(d, "id", None)]
    existentes_por_detalle = {}
    if detalle_ids:
        rows_det = (
            SolicitudFondosItem.query
            .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
            .filter(SolicitudFondosItem.sueldo_detalle_id.in_(detalle_ids))
            .all()
        )
        for it in rows_det:
            if it.sueldo_detalle_id is not None:
                existentes_por_detalle[int(it.sueldo_detalle_id)] = it

    creados = 0
    actualizados = 0
    omitidos = 0

    # ==========================================================
    # Integración idempotente
    # ==========================================================
    for d in detalles:
        if not d.trabajador_id:
            omitidos += 1
            continue

        det_id = int(d.id)
        it = existentes_por_detalle.get(det_id)

        if it is None:
            k = (int(d.trabajador_id or 0), int(d.contrato_id or 0), periodo_tag)
            it = idx_premium.get(k)

        if it is not None:
            it.seccion = "REMU"
            it.concepto = "SUELDO"
            it.trabajador_id = d.trabajador_id
            it.contrato_id = d.contrato_id
            it.monto = d.liquido
            it.descripcion = descripcion_std
            it.control_interno = periodo_tag
            it.orden = 1
            it.sueldo_nomina_id = nomina.id
            it.sueldo_detalle_id = d.id
            actualizados += 1
            continue

        item = SolicitudFondosItem(
            solicitud_id=solicitud.id,
            seccion="REMU",
            trabajador_id=d.trabajador_id,
            contrato_id=d.contrato_id,
            monto=d.liquido,
            concepto="SUELDO",
            descripcion=descripcion_std,
            control_interno=periodo_tag,
            orden=1,
            sueldo_nomina_id=nomina.id,
            sueldo_detalle_id=d.id,
        )
        db.session.add(item)
        creados += 1

    # ==========================================================
    # Commit seguro (anti 500)
    # ==========================================================
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "Se detectaron sueldos ya integrados en esta Solicitud (anti-duplicado). "
            "Vuelve a intentar; el sistema actualiza en vez de duplicar.",
            "warning",
        )
        return redirect(next_url)

    msg_extra = f" · {borrados} eliminados" if wipe_remu else ""
    flash(
        f"Integración completada: {creados} creados · {actualizados} actualizados · {omitidos} omitidos{msg_extra}.",
        "success",
    )
    return redirect(next_url)






@bp.get("/imprimir_cc.pdf")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def imprimir_cc_pdf():
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        flash(
            "Motor PDF no disponible (falta WeasyPrint o dependencias). "
            "Instala WeasyPrint en el contenedor para habilitar impresión PRO.",
            "error",
        )
        return redirect(url_for("sueldos.listado"))

    cc = _upper(request.args.get("centro_costo"))
    periodo = (request.args.get("periodo") or "").strip()  # YYYY-MM

    if not cc or not periodo:
        flash("Debes indicar Centro de Costo y Período (YYYY-MM).", "warning")
        return redirect(url_for("sueldos.listado"))

    try:
        anio = int(periodo.split("-")[0])
        mes = int(periodo.split("-")[1])
    except Exception:
        flash("Período inválido. Usa formato YYYY-MM (ej: 2026-01).", "warning")
        return redirect(url_for("sueldos.listado", centro_costo=cc))

    # Seguridad por CC
    if not current_user.has_role("ADMIN"):
        allowed_obras = _allowed_obras_for_user_ids()
        if not allowed_obras:
            abort(403)

        allowed_cc = {
            str(x or "").strip().upper()
            for (x,) in (
                db.session.query(func.coalesce(Obra.centro_costo, ""))
                .filter(Obra.id.in_(sorted(allowed_obras)))
                .distinct()
                .all()
            )
            if str(x or "").strip()
        }
        if cc not in allowed_cc:
            abort(403)

    # Traer todas las nóminas del CC/período
    nominas = (
        SueldoNomina.query
        .filter(SueldoNomina.centro_costo == cc)
        .filter(SueldoNomina.anio == anio, SueldoNomina.mes == mes)
        .order_by(SueldoNomina.empleador_id.asc(), SueldoNomina.id.asc())
        .all()
    )
    if not nominas:
        flash(f"No hay nóminas para {cc} en {periodo}.", "info")
        return redirect(url_for("sueldos.listado", centro_costo=cc, periodo=periodo))

    nomina_ids = [n.id for n in nominas]

    def format_rut(rut_str: str | None) -> str:
        if not rut_str:
            return "-"
        s = str(rut_str).strip()
        if "-" not in s:
            return s
        num, dv = s.split("-", 1)
        num = "".join(ch for ch in num if ch.isdigit())
        if not num:
            return s
        parts = []
        while len(num) > 3:
            parts.insert(0, num[-3:])
            num = num[:-3]
        parts.insert(0, num)
        return f"{'.'.join(parts)}-{dv.strip()}"

    tipo_key = _tipo_key_expr()
    tipo_prio = _tipo_priority_expr(tipo_key)

    q = (
        db.session.query(
            SueldoDetalle,
            SueldoNomina,
            Empleador.razon_social.label("empleador_rs"),
            Trabajador.tipo_trabajador.label("tipo_trabajador"),
            Trabajador.ap_paterno.label("ap_paterno"),
            Trabajador.ap_materno.label("ap_materno"),
            Trabajador.nombres.label("nombres"),
        )
        .join(SueldoNomina, SueldoNomina.id == SueldoDetalle.nomina_id)
        .join(Empleador, Empleador.id == SueldoNomina.empleador_id)
        .outerjoin(Trabajador, Trabajador.id == SueldoDetalle.trabajador_id)
        .filter(SueldoDetalle.nomina_id.in_(nomina_ids))
        .filter(SueldoDetalle.estado_linea == "OK")
        .filter(func.coalesce(SueldoDetalle.liquido, 0) > 0)
    )

    rows = (
        q.order_by(
            tipo_prio.asc(),
            tipo_key.asc(),
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            func.coalesce(SueldoDetalle.nombre_completo, "").asc(),
            SueldoDetalle.contrato_id.asc(),
            SueldoDetalle.id.asc(),
        )
        .all()
    )

    detalles = []
    total_anticipo = 0.0
    total_liquido = 0.0
    total_alcance_liquido = 0.0

    for d, nom, empleador_rs, tipo_trabajador, ap_paterno, ap_materno, nombres in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        rut_fmt = format_rut(d.rut) if d.rut else "-"

        cargo_nombre = "-"
        if d.trabajador and getattr(d.trabajador, "cargo", None) and getattr(d.trabajador.cargo, "nombre", None):
            cargo_nombre = d.trabajador.cargo.nombre

        anticipo = float(d.anticipo or 0)
        liquido = float(d.liquido or 0)
        alcance_liquido = anticipo + liquido

        detalles.append({
            "d": d,
            "nomina": nom,
            "rut_fmt": rut_fmt,
            "nombre_ordenado": nombre_ordenado,
            "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
            "cargo_nombre": cargo_nombre or "-",
            "empleador_rs": empleador_rs or "-",
            "anticipo": anticipo,
            "liquido": liquido,
            "alcance_liquido": alcance_liquido,
        })

        total_anticipo += anticipo
        total_liquido += liquido
        total_alcance_liquido += alcance_liquido

    try:
        html = render_template(
            "sueldos/sueldos_imprimir_cc_pdf.html",
            centro_costo=cc,
            periodo=periodo,
            nominas=nominas,
            detalles=detalles,
            total_anticipo=total_anticipo,
            total_liquido=total_liquido,
            total_alcance_liquido=total_alcance_liquido,
        )
    except TemplateError as e:
        flash(f"Error template impresión PDF: {e}", "error")
        return redirect(url_for("sueldos.listado", centro_costo=cc, periodo=periodo))

    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    filename = f"sueldos_{periodo}_{cc}.pdf".replace(" ", "_")
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Surrogate-Control"] = "no-store"
    return resp