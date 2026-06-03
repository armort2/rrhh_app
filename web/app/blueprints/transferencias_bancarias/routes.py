# web/app/blueprints/transferencias_bancarias/routes.py
from __future__ import annotations

import json
import re
import uuid
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import login_required
from sqlalchemy import or_

from . import bp  # ✅ IMPORTANTE: usamos el bp definido en __init__.py
from ...models import Trabajador, Tercero
from ...services.bank_nominas import (
    BankRow,
    build_xlsx_from_template,
    get_template_path,
    TEMPLATE_TRANSFER_MAS,
    rut_plain_from_parts,
)


# ---------------------------
# Helpers
# ---------------------------

def _q_norm(s: str) -> str:
    return (s or "").strip()


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _periodo_default() -> str:
    hoy = date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"

def _bank_sanitize_text(s: str) -> str:
    """
    Sanitiza texto para archivo bancario:
    - Reemplaza coma por espacio (para nombres "Apellido, Nombre")
    - Quita tildes/diacríticos y convierte ñ/Ñ -> n/N
    - Normaliza espacios
    """
    s = (s or "").strip()
    if not s:
        return ""

    # 1) Sin comas
    s = s.replace(",", " ")

    # 2) Normaliza unicode y elimina diacríticos (tildes) + ñ/Ñ
    # NFKD separa letra + acento, luego removemos los acentos
    s_norm = unicodedata.normalize("NFKD", s)
    s_no_marks = "".join(ch for ch in s_norm if not unicodedata.combining(ch))

    # 3) Limpieza final de espacios
    s_no_marks = re.sub(r"\s+", " ", s_no_marks).strip()
    return s_no_marks

# ---------------------------
# Views
# ---------------------------

@bp.get("/")
@login_required
def listado():
    """
    Entrada del módulo.
    Mantiene compatibilidad con el link del menú:
      url_for('transferencias_bancarias.listado')
    """
    return redirect(url_for("transferencias_bancarias.crear"))


@bp.route("/crear", methods=["GET", "POST"])
@login_required
def crear():
    """
    GET  -> render del formulario premium
    POST -> recibe items_json, arma BankRow con glosa por fila y genera XLSX.
    """
    if request.method == "GET":
        today = date.today()
        return render_template(
            "transferencias_bancarias/crear.html",
            default_periodo=_periodo_default(),
            anio=today.year,
            mes=today.month,
        )

    # POST
    try:
        anio = int(request.form.get("anio") or 0)
        mes = int(request.form.get("mes") or 0)
    except Exception:
        anio, mes = 0, 0

    # Cuenta origen fija (Santander Transferencias Masivas)
    cuenta_origen = "5555555555"
    glosa_default = (request.form.get("glosa_default") or "").strip()

    if not (2000 <= anio <= 2100):
        flash("Año inválido.", "danger")
        return redirect(url_for("transferencias_bancarias.crear"))

    if not (1 <= mes <= 12):
        flash("Mes inválido.", "danger")
        return redirect(url_for("transferencias_bancarias.crear"))

    raw = request.form.get("items_json") or "[]"
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            items = []
    except Exception:
        items = []

    if not items:
        flash("No hay registros para generar la nómina.", "warning")
        return redirect(url_for("transferencias_bancarias.crear"))

    rows: List[BankRow] = []
    excluidos: List[Dict[str, Any]] = []

    for it in items:
        try:
            rut_plain = (it.get("rut_plain") or "").strip()
            nombre_raw = (it.get("nombre") or "").strip()
            banco_code = (it.get("banco_code") or "").strip()
            cuenta = (it.get("cuenta") or "").strip()
            email = (it.get("email") or "").strip() or "transferencias@grupo-cs.cl"
            monto = Decimal(str(it.get("monto") or "0"))
            glosa_row_raw = (it.get("glosa") or "").strip() or glosa_default

            # ✅ Sanitización para archivo bancario
            nombre = _bank_sanitize_text(nombre_raw)
            glosa_row = _bank_sanitize_text(glosa_row_raw)

            if not rut_plain or not nombre or not banco_code or not cuenta or monto <= 0:
                excluidos.append({"item": it, "motivo": "Faltan datos o monto <= 0"})
                continue

            rows.append(
                BankRow(
                    rut_beneficiario=rut_plain,
                    nombre_beneficiario=nombre,
                    monto=monto,
                    codigo_banco=banco_code,
                    cuenta_destino=cuenta,
                    email_beneficiario=email,
                    glosa=glosa_row,
                )
            )

        except Exception as e:
            excluidos.append({"item": it, "motivo": f"Error parseando item: {e}"})
            continue

    if not rows:
        flash("Todos los registros fueron inválidos (faltan datos bancarios o montos).", "danger")
        return redirect(url_for("transferencias_bancarias.crear"))

    template_path = get_template_path(current_app.root_path, TEMPLATE_TRANSFER_MAS)
    wb = build_xlsx_from_template(
        template_path=template_path,
        template_kind="TRANSFER_MAS",
        rows=rows,
        anio=anio,
        mes=mes,
        glosa=glosa_default or None,
        cuenta_origen_transfer_mas=cuenta_origen,
    )

    tmp_dir = Path(current_app.instance_path) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{anio:04d}-{mes:02d} Transferencias Masivas - Extras.xlsx"
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}_{filename}"
    wb.save(tmp_path)

    if excluidos:
        flash(f"Nómina generada. Excluidos: {len(excluidos)} (por datos inválidos).", "warning")
    else:
        flash("Nómina generada correctamente.", "success")

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_age=0,
    )


# ---------------------------
# API: Autocomplete beneficiarios
# ---------------------------

@bp.get("/api/buscar-beneficiario")
@login_required
def api_buscar_beneficiario():
    q = _q_norm(request.args.get("q", ""))
    if not q or len(q) < 2:
        return jsonify({"results": []})

    q_like = f"%{q}%"
    q_digits = _digits_only(q)

    # Trabajadores
    t_filters = [
        Trabajador.nombres.ilike(q_like),
        Trabajador.ap_paterno.ilike(q_like),
        Trabajador.ap_materno.ilike(q_like),
        Trabajador.rut.ilike(q_like),
    ]
    if q_digits:
        t_filters.append(Trabajador.rut.ilike(f"%{q_digits}%"))

    trabajadores = (
        Trabajador.query
        .filter(or_(*t_filters))
        .limit(15)
        .all()
    )

    # Terceros
    x_filters = [
        Tercero.nombres.ilike(q_like),
        Tercero.ap_paterno.ilike(q_like),
        Tercero.ap_materno.ilike(q_like),
    ]
    if q_digits:
        try:
            x_filters.append(Tercero.rut_num == int(q_digits))
        except Exception:
            pass

    terceros = (
        Tercero.query
        .filter(or_(*x_filters))
        .limit(15)
        .all()
    )

    out: List[Dict[str, Any]] = []

    for t in trabajadores:
        banco_code = (t.banco.codigo_sbif if getattr(t, "banco", None) else "") or ""
        cuenta_raw = (getattr(t, "cuenta_numero", None) or getattr(t, "cuenta_rut", None) or "") or ""
        cuenta_plain = re.sub(r"\D", "", cuenta_raw)

        out.append({
            "kind": "TRABAJADOR",
            "id": t.id,
            "label": f"{t.ap_paterno} {t.ap_materno or ''}, {t.nombres} · {getattr(t, 'rut_completo', '')}".strip(),
            "rut_plain": rut_plain_from_parts(getattr(t, "rut", None), getattr(t, "dv", None)) or "",
            "nombre": f"{t.ap_paterno} {t.ap_materno or ''}, {t.nombres}".strip(),
            "banco_code": banco_code,
            "cuenta": cuenta_plain,
            "email": (getattr(t, "correo", None) or "").strip() or "transferencias@grupo-cs.cl",
        })

    for x in terceros:
        banco_code = (x.banco.codigo_sbif if getattr(x, "banco", None) else "") or ""
        cuenta_plain = re.sub(r"\D", "", (getattr(x, "cuenta_numero", None) or "") or "")

        out.append({
            "kind": "TERCERO",
            "id": x.id,
            "label": f"{getattr(x, 'nombre_display', '')} · {getattr(x, 'rut_completo', '')}".strip(),
            "rut_plain": rut_plain_from_parts(str(getattr(x, "rut_num", "") or ""), getattr(x, "dv", None)) or "",
            "nombre": getattr(x, "nombre_display", None) or "-",
            "banco_code": banco_code,
            "cuenta": cuenta_plain,
            "email": (getattr(x, "correo", None) or "").strip() or "transferencias@grupo-cs.cl",
        })

    q_low = q.lower()
    out.sort(key=lambda r: (0 if r["label"].lower().startswith(q_low) else 1, r["label"].lower()))

    return jsonify({"results": out[:20]})