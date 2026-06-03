# web/app/services/egresos_docs.py
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

from flask import current_app
from docx import Document as DocxDocument

from ..models import Egreso
from .docx_engine import replace_placeholders
from .paths_nextcloud import get_nc_paths


TEMPLATE_REL_PATH = "document_templates/solicitudes/egreso.docx"


def _fmt_fecha_es(d: date) -> str:
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


def _fmt_clp(v: Decimal | float | int | str | None) -> str:
    if v is None:
        n = 0
    else:
        try:
            n = int(Decimal(str(v)))
        except Exception:
            n = 0
    s = f"{n:,}".replace(",", ".")
    return f"${s}"


def _fmt_clp_blank_if_zero(v: Decimal | float | int | str | None) -> str:
    if v is None:
        return ""
    try:
        n = int(Decimal(str(v)))
    except Exception:
        n = 0
    if n == 0:
        return ""
    s = f"{n:,}".replace(",", ".")
    return f"${s}"


def _fmt_rut_cl(rut: str | None, dv: str | None = None) -> str:
    s = (rut or "").strip().upper()
    if not s:
        return ""
    s2 = re.sub(r"[^0-9K]", "", s)

    body = ""
    dv2 = (dv or "").strip().upper() if dv is not None else ""

    if dv is None:
        if len(s2) >= 2:
            body, dv2 = s2[:-1], s2[-1]
        else:
            body = s2
            dv2 = ""
    else:
        body = s2

    body = body.strip()
    dv2 = dv2.strip().upper()

    if not body:
        return ""

    try:
        body_i = int(body)
        body_fmt = f"{body_i:,}".replace(",", ".")
    except Exception:
        body_fmt = body

    return f"{body_fmt}-{dv2}" if dv2 else body_fmt


_UNIDADES = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
_DECENAS_ESPECIALES = {
    10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
}
_DECENAS = ["", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CIENTOS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
            "seiscientos", "setecientos", "ochocientos", "novecientos"]


def _n_0_999(n: int) -> str:
    if n == 0:
        return "cero"
    if n == 100:
        return "cien"
    parts = []
    c = n // 100
    r = n % 100
    if c:
        parts.append(_CIENTOS[c])
    if r:
        if r < 10:
            parts.append(_UNIDADES[r])
        elif 10 <= r <= 19:
            parts.append(_DECENAS_ESPECIALES[r])
        else:
            d = r // 10
            u = r % 10
            if d == 2 and u != 0:
                parts.append("veinti" + _UNIDADES[u])
            else:
                if _DECENAS[d]:
                    if u == 0:
                        parts.append(_DECENAS[d])
                    else:
                        parts.append(f"{_DECENAS[d]} y {_UNIDADES[u]}")
                else:
                    parts.append(_UNIDADES[u])
    return " ".join([p for p in parts if p]).strip()


def numero_a_palabras_cl(n: int) -> str:
    if n < 0:
        return "menos " + numero_a_palabras_cl(abs(n))
    if n < 1000:
        return _n_0_999(n)
    if n < 1_000_000:
        miles = n // 1000
        resto = n % 1000
        base = "mil" if miles == 1 else f"{_n_0_999(miles)} mil"
        return (base + (" " + _n_0_999(resto) if resto else "")).strip()
    if n < 1_000_000_000:
        millones = n // 1_000_000
        resto = n % 1_000_000
        base = "un millón" if millones == 1 else f"{numero_a_palabras_cl(millones)} millones"
        return (base + (" " + numero_a_palabras_cl(resto) if resto else "")).strip()
    return str(n)


def _safe_filename(s: str) -> str:
    keep = []
    for ch in (s or ""):
        if ch.isalnum() or ch in (" ", "-", "_", "."):
            keep.append(ch)
    out = "".join(keep).strip()
    out = re.sub(r"\s+", " ", out)
    return out or "EGRESO"


def _docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    """
    Convierte DOCX a PDF usando LibreOffice (soffice).
    Requiere paquete libreoffice instalado en el contenedor.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "soffice",
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(out_dir),
        str(docx_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise RuntimeError("No se encontró 'soffice'. Instala LibreOffice en el contenedor web.") from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", errors="ignore")
        raise RuntimeError(f"Error convirtiendo DOCX a PDF (soffice): {err}") from e

    # LibreOffice genera <mismo_nombre>.pdf en outdir
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError("La conversión a PDF terminó sin error, pero no se encontró el PDF generado.")
    return pdf_path


def _guardar_en_carpeta_trabajador_egresos(egreso: Egreso, docx_path: Path, pdf_path: Path | None) -> tuple[str | None, str | None]:
    """
    Si el beneficiario es trabajador, copia archivos a:
      /<CENTRO_DE_COSTO>/Laboral/Trabajadores/<Ap Pat> <Ap Mat> <Nombres>/EGRESOS/
    """
    if egreso.trabajador_id is None or getattr(egreso, "trabajador", None) is None:
        return (None, None)

    t = egreso.trabajador

    # Centro de costo: idealmente desde la obra del egreso (porque el egreso tiene contexto obra)
    centro_costo = ""
    if getattr(egreso, "obra", None) is not None:
        centro_costo = (getattr(egreso.obra, "centro_costo", "") or "").strip()

    # fallback si por alguna razón no hay obra/código
    if not centro_costo:
        # si tu Obra no tiene codigo, puedes probar con otro campo (ej: centro_costo)
        centro_costo = "SIN_NOMBRE"

    nc = get_nc_paths()
    destino_dir = nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=(t.nombres or ""),
        ap_paterno=(t.ap_paterno or ""),
        ap_materno=(t.ap_materno or ""),
        tipo_doc="EGRESOS",
    )

    destino_dir.mkdir(parents=True, exist_ok=True)

    dst_docx = destino_dir / docx_path.name
    shutil.copy2(docx_path, dst_docx)

    dst_pdf = None
    if pdf_path is not None:
        dst_pdf = destino_dir / pdf_path.name
        shutil.copy2(pdf_path, dst_pdf)

    return (str(dst_docx), str(dst_pdf) if dst_pdf else None)


def generar_docx_y_pdf_egreso(egreso: Egreso) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    """
    Genera DOCX desde plantilla, genera PDF y (si trabajador) guarda copia en carpeta EGRESOS del trabajador.
    Retorna:
      (docx_tmp_path, docx_nombre, pdf_tmp_path, pdf_nombre, docx_guardado_path, pdf_guardado_path)
    """
    app_root = Path(current_app.root_path)  # web/app
    tpl_path = app_root / TEMPLATE_REL_PATH
    if not tpl_path.exists():
        raise FileNotFoundError(f"No existe plantilla: {tpl_path}")

    doc = DocxDocument(str(tpl_path))

    es_externo = egreso.trabajador_id is None

    emp_rs = ""
    emp_rut_raw = ""
    emp_dv = None
    obra_nom = ""

    if getattr(egreso, "empleador", None) is not None:
        emp = egreso.empleador
        emp_rs = (getattr(emp, "razon_social", "") or "")
        emp_rut_raw = (getattr(emp, "rut", "") or "")
        emp_dv = getattr(emp, "dv", None)

    if getattr(egreso, "obra", None) is not None:
        obra = egreso.obra
        obra_nom = (getattr(obra, "nombre", "") or "")

    emp_rut = _fmt_rut_cl(emp_rut_raw, emp_dv)

    trab_nombre = ""
    trab_rut = ""
    trab_nombres = ""
    trab_ap_pat = ""
    trab_ap_mat = ""

    if not es_externo and getattr(egreso, "trabajador", None) is not None:
        t = egreso.trabajador
        trab_nombres = (t.nombres or "")
        trab_ap_pat = (t.ap_paterno or "")
        trab_ap_mat = (t.ap_materno or "")
        trab_nombre = f"{trab_ap_pat} {trab_ap_mat}, {trab_nombres}".strip().strip(",")
        trab_rut = _fmt_rut_cl(getattr(t, "rut", None), getattr(t, "dv", None))

    pagado_a_nombre = (egreso.pagado_a_nombre or "") if es_externo else trab_nombre

    pagado_a_rut_raw = (egreso.pagado_a_rut or "") if es_externo else trab_rut
    pagado_a_rut = _fmt_rut_cl(pagado_a_rut_raw, None) if pagado_a_rut_raw else ""

    # ✅ Compatibilidad plantilla: si es EXTERNO, la plantilla usa TRABAJADOR_*,
    # así que “inyectamos” los datos del externo en esos tags.
    if es_externo:
        # En externos no tenemos estructura apellidos/nombres, así que dejamos
        # todo el nombre en TRABAJADOR_NOMBRES y apellidos vacíos.
        trab_nombres = (pagado_a_nombre or "").strip()
        trab_ap_pat = ""
        trab_ap_mat = ""
        trab_rut = (pagado_a_rut or "").strip()

    items_by_orden = {i.orden: i for i in (egreso.items or [])}
    total = Decimal("0")
    placeholders: dict[str, str] = {}

    for i in range(1, 6):
        it = items_by_orden.get(i)
        item_txt = ((it.item or "").strip() if it else "")
        monto_raw = (it.monto if (it is not None and it.monto is not None) else None)

        try:
            monto_dec = Decimal(str(monto_raw)) if monto_raw is not None else Decimal("0")
        except Exception:
            monto_dec = Decimal("0")

        total += monto_dec

        if not item_txt and monto_dec == 0:
            item_txt_out = ""
            monto_txt_out = ""
        else:
            item_txt_out = item_txt
            monto_txt_out = _fmt_clp_blank_if_zero(monto_dec)

        placeholders[f"EGRESO_ITEM_{i}"] = item_txt_out
        placeholders[f"EGRESO_ITEM {i}"] = item_txt_out
        placeholders[f"EGRESO_MONTO_{i}"] = monto_txt_out

    total_int = int(total)
    placeholders.update({
        "EGRESO_N": str(egreso.numero or ""),
        "EGRESO_FECHA": _fmt_fecha_es(egreso.fecha_egreso),
        "EGRESO_MOTIVO": egreso.motivo or "",
        "EGRESO_SOLICITANTE": egreso.solicitante or "",
        "EGRESO_SOLICITANTE_CARGO": egreso.solicitante_cargo or "",

        "EGRESO_TOTAL": _fmt_clp(total_int),
        "EGRESO_TOTAL_PALABRAS": (numero_a_palabras_cl(total_int) + " pesos").upper(),

        "EMPLEADOR_RAZON_SOCIAL": emp_rs,
        "EMPLEADOR_RUT": emp_rut,
        "OBRA_NOMBRE": obra_nom,

        "PAGADO_A_NOMBRE": pagado_a_nombre,
        "PAGADO_A_RUT": pagado_a_rut,

        "TRABAJADOR_NOMBRES": trab_nombres,
        "TRABAJADOR_AP_PATERNO": trab_ap_pat,
        "TRABAJADOR_AP_MATERNO": trab_ap_mat,
        "TRABAJADOR_RUT": trab_rut,
    })

    replace_placeholders(doc, placeholders)

    # Naming corporativo
    fecha_iso = (egreso.fecha_egreso or date.today()).isoformat()
    if not es_externo and getattr(egreso, "trabajador", None) is not None:
        # Orden corporativo: Apellidos + Nombres
        full_name = " ".join(
            p for p in [
                trab_ap_pat,
                trab_ap_mat,
                trab_nombres,
            ]
            if p
        ).strip()
    else:
        full_name = (egreso.pagado_a_nombre or "Externo").strip()

    full_name = _safe_filename(full_name)
    # Naming corporativo (incluye número de egreso)
    nro = egreso.numero or ""

    docx_name = re.sub(
        r"\s+",
        " ",
        f"{fecha_iso} Egreso N° {nro} - {full_name}.docx"
    ).strip()

    pdf_name = re.sub(
        r"\s+",
        " ",
        f"{fecha_iso} Egreso N° {nro} - {full_name}.pdf"
    ).strip()

    # Guardado local temporal (para descargas)
    out_dir = Path("/tmp/rrhh_docs/egresos")
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / docx_name
    doc.save(str(docx_path))

    # PDF
    pdf_tmp_path = _docx_to_pdf(docx_path, out_dir)

    # Renombrar PDF al naming esperado (LibreOffice puede generar el mismo stem, pero aseguramos)
    pdf_path = out_dir / pdf_name
    if pdf_tmp_path != pdf_path:
        try:
            if pdf_path.exists():
                pdf_path.unlink()
            pdf_tmp_path.rename(pdf_path)
        except Exception:
            # fallback: copia y listo
            shutil.copy2(pdf_tmp_path, pdf_path)

    # Copia a carpeta del trabajador/EGRESOS (si aplica)
    docx_guardado, pdf_guardado = _guardar_en_carpeta_trabajador_egresos(egreso, docx_path, pdf_path)

    return (
        str(docx_path), docx_name,
        str(pdf_path), pdf_name,
        docx_guardado, pdf_guardado
    )


# Compat: si en algún lado aún llamas a generar_docx_egreso()
def generar_docx_egreso(egreso: Egreso) -> tuple[str, str]:
    docx_path, docx_name, _, _, _, _ = generar_docx_y_pdf_egreso(egreso)
    return docx_path, docx_name