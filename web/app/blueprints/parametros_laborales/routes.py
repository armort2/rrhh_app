# web/app/blueprints/parametros_laborales/routes.py
from __future__ import annotations

from datetime import date, datetime

from pathlib import Path
from werkzeug.utils import secure_filename
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from flask_login import login_required

from ...extensions import db
from ...models import ParametroLaboral
from ...services.parametros_laborales import (
    existe_parametro_periodo,
    normalizar_periodo,
    obtener_ultimo_parametro,
)
from ...services.previred_import import parse_previred_pdf

bp = Blueprint("parametros_laborales", __name__, url_prefix="/parametros-laborales")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _parse_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    return None


def _to_decimal_or_none(raw: str | None):
    s = (raw or "").strip()
    if not s:
        return None

    # Acepta:
    # 39.790,63 -> 39790.63
    # 39790.63  -> 39790.63
    # 39790     -> 39790
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return s  # SQLAlchemy Numeric acepta string numérico sin problema
    except Exception:
        return None


def _parametros_form_to_dict() -> dict:
    return {
        "periodo": normalizar_periodo(request.form.get("periodo")),
        "fecha_vigencia_desde": _parse_date(request.form.get("fecha_vigencia_desde")),
        "fecha_vigencia_hasta": _parse_date(request.form.get("fecha_vigencia_hasta")),

        "uf": _to_decimal_or_none(request.form.get("uf")),
        "utm": _to_decimal_or_none(request.form.get("utm")),
        "uta": _to_decimal_or_none(request.form.get("uta")),

        "renta_minima_dependiente": _to_decimal_or_none(request.form.get("renta_minima_dependiente")),
        "renta_minima_menor_mayor65": _to_decimal_or_none(request.form.get("renta_minima_menor_mayor65")),
        "renta_minima_no_remuneracional": _to_decimal_or_none(request.form.get("renta_minima_no_remuneracional")),

        "tope_imponible_afp": _to_decimal_or_none(request.form.get("tope_imponible_afp")),
        "tope_imponible_inp": _to_decimal_or_none(request.form.get("tope_imponible_inp")),
        "tope_imponible_seguro_cesantia": _to_decimal_or_none(request.form.get("tope_imponible_seguro_cesantia")),

        "gratificacion_25_por_ciento_tope_mensual": _to_decimal_or_none(request.form.get("gratificacion_25_por_ciento_tope_mensual")),
        "sueldo_minimo_para_gratificacion": _to_decimal_or_none(request.form.get("sueldo_minimo_para_gratificacion")),

        "fuente": (request.form.get("fuente") or "").strip() or None,
        "fuente_documento": (request.form.get("fuente_documento") or "").strip() or None,
        "observaciones": (request.form.get("observaciones") or "").strip() or None,
    }


def _validar_payload(payload: dict, *, excluir_id: int | None = None) -> list[str]:
    errores: list[str] = []

    if not payload["periodo"]:
        errores.append("Debes indicar un período válido en formato YYYY-MM.")

    if not payload["fecha_vigencia_desde"]:
        errores.append("Debes indicar la fecha de vigencia desde.")

    if not payload["fecha_vigencia_hasta"]:
        errores.append("Debes indicar la fecha de vigencia hasta.")

    if payload["fecha_vigencia_desde"] and payload["fecha_vigencia_hasta"]:
        if payload["fecha_vigencia_hasta"] < payload["fecha_vigencia_desde"]:
            errores.append("La fecha de vigencia hasta no puede ser menor a la fecha de vigencia desde.")

    if payload["periodo"] and existe_parametro_periodo(payload["periodo"], excluir_id=excluir_id):
        errores.append(f"Ya existe un registro para el período {payload['periodo']}.")

    return errores

def _static_previred_dir() -> Path:
    """
    Carpeta destino para PDFs Previred subidos por el usuario.
    Queda dentro de static para trazabilidad simple.
    """
    base = Path(current_app.root_path) / "static" / "previred"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _vals_from_previred_result(parsed: dict) -> dict:
    sueldo_minimo = parsed.get("renta_minima_dependiente") or ""
    tope_mensual_grat = _calc_tope_gratificacion_mensual(sueldo_minimo)

    return {
        "periodo": parsed.get("periodo") or "",
        "fecha_vigencia_desde": parsed.get("fecha_vigencia_desde") or "",
        "fecha_vigencia_hasta": parsed.get("fecha_vigencia_hasta") or "",

        "uf": parsed.get("uf") or "",
        "utm": parsed.get("utm") or "",
        "uta": parsed.get("uta") or "",

        "renta_minima_dependiente": sueldo_minimo,
        "renta_minima_menor_mayor65": parsed.get("renta_minima_menor_mayor65") or "",
        "renta_minima_no_remuneracional": parsed.get("renta_minima_no_remuneracional") or "",

        "tope_imponible_afp": parsed.get("tope_imponible_afp") or "",
        "tope_imponible_inp": parsed.get("tope_imponible_inp") or "",
        "tope_imponible_seguro_cesantia": parsed.get("tope_imponible_seguro_cesantia") or "",

        "gratificacion_25_por_ciento_tope_mensual": tope_mensual_grat,
        "sueldo_minimo_para_gratificacion": sueldo_minimo,

        "fuente": parsed.get("fuente") or "PREVIRED",
        "fuente_documento": parsed.get("fuente_documento") or "",
        "observaciones": parsed.get("observaciones") or "",
    }

def _calc_tope_gratificacion_mensual(sueldo_minimo: str | None) -> str:
    """
    Tope mensual referencial para gratificación art. 50:
      (4,75 * IMM) / 12

    OJO:
    - La ley fija un tope anual de 4,75 IMM.
    - Aquí usamos una división mensual referencial para efectos operativos del sistema.
    """
    s = (sueldo_minimo or "").strip()
    if not s:
        return ""

    try:
        # Acepta "539000" o "539.000" o "539000.00"
        normalized = s.replace(".", "").replace(",", ".")
        imm = Decimal(normalized)

        anual = imm * Decimal("4.75")
        mensual = (anual / Decimal("12")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        return f"{int(mensual)}"
    except Exception:
        return ""

# ------------------------------------------------------------
# Listado
# ------------------------------------------------------------

@bp.get("/")
@login_required
def listado():
    rows = (
        ParametroLaboral.query
        .order_by(ParametroLaboral.periodo.desc(), ParametroLaboral.id.desc())
        .all()
    )

    ultimo = obtener_ultimo_parametro()

    return render_template(
        "parametros_laborales/listado.html",
        rows=rows,
        ultimo=ultimo,
    )


# ------------------------------------------------------------
# Importar Previred
# ------------------------------------------------------------

@bp.get("/importar-previred")
@login_required
def importar_previred():
    return render_template("parametros_laborales/importar_previred.html")


@bp.post("/importar-previred")
@login_required
def importar_previred_post():
    f = request.files.get("archivo_pdf")

    if not f or not getattr(f, "filename", ""):
        flash("Debes seleccionar un archivo PDF de Previred.", "error")
        return redirect(url_for("parametros_laborales.importar_previred"))

    filename = secure_filename(f.filename or "")
    if not filename.lower().endswith(".pdf"):
        flash("El archivo debe ser un PDF.", "error")
        return redirect(url_for("parametros_laborales.importar_previred"))

    try:
        target_dir = _static_previred_dir()
        target_path = target_dir / filename
        f.save(target_path)

        parsed = parse_previred_pdf(target_path).to_dict()
        vals = _vals_from_previred_result(parsed)

        periodo = vals.get("periodo") or ""
        existente = None
        if periodo:
            existente = ParametroLaboral.query.filter_by(periodo=periodo).first()

        if existente:
            flash(
                f"El período {periodo} ya existe. Se cargaron los datos del PDF para revisar y actualizar el registro existente.",
                "warning",
            )

            return render_template(
                "parametros_laborales/form.html",
                modo="editar",
                row=existente,
                vals=vals,
                importado_desde_previred=True,
                previred_pdf_nombre=filename,
                periodo_existente=True,
            )

        flash(
            "PDF Previred procesado correctamente. Revisa y confirma los datos antes de guardar.",
            "success",
        )

        return render_template(
            "parametros_laborales/form.html",
            modo="nuevo",
            row=None,
            vals=vals,
            importado_desde_previred=True,
            previred_pdf_nombre=filename,
            periodo_existente=False,
        )

    except Exception as e:
        current_app.logger.exception("Error importando PDF Previred")
        flash(f"No se pudo procesar el PDF Previred: {e}", "error")
        return redirect(url_for("parametros_laborales.importar_previred"))


# ------------------------------------------------------------
# Nuevo
# ------------------------------------------------------------

@bp.get("/nuevo")
@login_required
def nuevo():
    ultimo = obtener_ultimo_parametro()

    vals = {
        "periodo": "",
        "fecha_vigencia_desde": "",
        "fecha_vigencia_hasta": "",

        "uf": "",
        "utm": "",
        "uta": "",

        "renta_minima_dependiente": "",
        "renta_minima_menor_mayor65": "",
        "renta_minima_no_remuneracional": "",

        "tope_imponible_afp": "",
        "tope_imponible_inp": "",
        "tope_imponible_seguro_cesantia": "",

        "gratificacion_25_por_ciento_tope_mensual": "",
        "sueldo_minimo_para_gratificacion": "",

        "fuente": "MANUAL",
        "fuente_documento": "",
        "observaciones": "",
    }

    # UX: si existe último registro, prellenar varios campos
    if ultimo:
        vals.update({
            "uf": str(ultimo.uf or ""),
            "utm": str(ultimo.utm or ""),
            "uta": str(ultimo.uta or ""),
            "renta_minima_dependiente": str(ultimo.renta_minima_dependiente or ""),
            "renta_minima_menor_mayor65": str(ultimo.renta_minima_menor_mayor65 or ""),
            "renta_minima_no_remuneracional": str(ultimo.renta_minima_no_remuneracional or ""),
            "tope_imponible_afp": str(ultimo.tope_imponible_afp or ""),
            "tope_imponible_inp": str(ultimo.tope_imponible_inp or ""),
            "tope_imponible_seguro_cesantia": str(ultimo.tope_imponible_seguro_cesantia or ""),
            "gratificacion_25_por_ciento_tope_mensual": str(ultimo.gratificacion_25_por_ciento_tope_mensual or ""),
            "sueldo_minimo_para_gratificacion": str(ultimo.sueldo_minimo_para_gratificacion or ""),
        })

    return render_template(
        "parametros_laborales/form.html",
        modo="nuevo",
        row=None,
        vals=vals,
    )


@bp.post("/nuevo")
@login_required
def nuevo_post():
    payload = _parametros_form_to_dict()
    errores = _validar_payload(payload)

    if errores:
        for e in errores:
            flash(e, "error")
        return render_template(
            "parametros_laborales/form.html",
            modo="nuevo",
            row=None,
            vals={k: ("" if v is None else str(v)) for k, v in payload.items()},
        )

    row = ParametroLaboral(**payload)
    db.session.add(row)
    db.session.commit()

    flash(f"Parámetro laboral {row.periodo} creado correctamente.", "success")
    return redirect(url_for("parametros_laborales.listado"))


# ------------------------------------------------------------
# Editar
# ------------------------------------------------------------

@bp.get("/<int:parametro_id>/editar")
@login_required
def editar(parametro_id: int):
    row = ParametroLaboral.query.get_or_404(parametro_id)

    vals = {
        "periodo": row.periodo or "",
        "fecha_vigencia_desde": row.fecha_vigencia_desde.isoformat() if row.fecha_vigencia_desde else "",
        "fecha_vigencia_hasta": row.fecha_vigencia_hasta.isoformat() if row.fecha_vigencia_hasta else "",

        "uf": str(row.uf or ""),
        "utm": str(row.utm or ""),
        "uta": str(row.uta or ""),

        "renta_minima_dependiente": str(row.renta_minima_dependiente or ""),
        "renta_minima_menor_mayor65": str(row.renta_minima_menor_mayor65 or ""),
        "renta_minima_no_remuneracional": str(row.renta_minima_no_remuneracional or ""),

        "tope_imponible_afp": str(row.tope_imponible_afp or ""),
        "tope_imponible_inp": str(row.tope_imponible_inp or ""),
        "tope_imponible_seguro_cesantia": str(row.tope_imponible_seguro_cesantia or ""),

        "gratificacion_25_por_ciento_tope_mensual": str(row.gratificacion_25_por_ciento_tope_mensual or ""),
        "sueldo_minimo_para_gratificacion": str(row.sueldo_minimo_para_gratificacion or ""),

        "fuente": row.fuente or "",
        "fuente_documento": row.fuente_documento or "",
        "observaciones": row.observaciones or "",
    }

    return render_template(
        "parametros_laborales/form.html",
        modo="editar",
        row=row,
        vals=vals,
    )


@bp.post("/<int:parametro_id>/editar")
@login_required
def editar_post(parametro_id: int):
    row = ParametroLaboral.query.get_or_404(parametro_id)

    payload = _parametros_form_to_dict()
    errores = _validar_payload(payload, excluir_id=row.id)

    if errores:
        for e in errores:
            flash(e, "error")
        return render_template(
            "parametros_laborales/form.html",
            modo="editar",
            row=row,
            vals={k: ("" if v is None else str(v)) for k, v in payload.items()},
        )

    for k, v in payload.items():
        setattr(row, k, v)

    db.session.commit()

    flash(f"Parámetro laboral {row.periodo} actualizado correctamente.", "success")
    return redirect(url_for("parametros_laborales.listado"))