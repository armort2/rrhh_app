# web/app/services/extras_docs.py
from __future__ import annotations

import re
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from flask import current_app
from docx import Document as DocxDocument

from ..models.extras_remu import ExtraRemuItem
from ..utils import fecha_larga_es
from .docx_engine import replace_placeholders
from .num_to_words_es import clp_a_palabras
from .paths_nextcloud import get_nc_paths
from .pdf_convert import convert_docx_to_pdf
from .rut_format import rut_con_puntos
from .storage_nextcloud_fs import ensure_dir
from .date_format import fecha_larga_el

TPL_BONO_REL = "document_templates/extras/anexo_bono.docx"
TPL_TRATO_REL = "document_templates/extras/anexo_trato.docx"
TPL_SABADO_REL = "document_templates/extras/anexo_sabado.docx"
TPL_HORAS_EXTRA_REL = "document_templates/extras/anexo_horas_extra.docx"


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "ANEXO"


def _ultimo_dia_mes(anio: int, mes: int) -> date:
    if mes == 12:
        return date(anio, 12, 31)
    return date(anio, mes + 1, 1) - timedelta(days=1)


def _fmt_fecha_corta(d: date | None) -> str:
    """DD-MM-YYYY (para placeholders EXTRA_PERIODO_DESDE/HASTA)."""
    return d.strftime("%d-%m-%Y") if d else ""

def _pretty_bono_codigo(codigo: str) -> str:
    """
    Convierte códigos internos tipo 'BONO_DESEMPENO' a 'Bono desempeño'.
    - Si viene ya humanizado (ej: 'Bono desempeño'), lo respeta.
    """
    raw = (codigo or "").strip()
    if not raw:
        return ""

    # Si ya viene con espacios o minúsculas, asumimos "bonito"
    if any(ch.islower() for ch in raw) or " " in raw:
        return raw

    s = raw.strip().lower().replace("-", "_")
    s = s.replace("_", " ").strip()

    # pequeñas correcciones típicas (sin ponernos poetas)
    s = s.replace("desempeno", "desempeño")
    s = s.replace("produccion", "producción")

    # Capitalizamos estilo documento: "Bono desempeño"
    return s[:1].upper() + s[1:] if s else ""

def _fmt_clp(v: Decimal | int | float | str | None) -> str:
    if v is None:
        n = 0
    else:
        try:
            n = int(Decimal(str(v)))
        except Exception:
            n = 0
    return f"${f'{n:,}'.replace(',', '.')}"


def _tpl_for_item(item: ExtraRemuItem) -> Path:
    """
    Selección de plantilla:
    - Preferimos concepto_tipo (más estable que concepto_codigo cuando BONO usa códigos internos).
    - Para JORNADA_EXTRAORDINARIA miramos el concepto_codigo (SABADO/HORAS_EXTRA).
    """
    app_root = Path(current_app.root_path)

    concepto_tipo = (getattr(item, "concepto_tipo", "") or "").strip().upper()
    concepto_codigo = (getattr(item, "concepto_codigo", "") or "").strip().upper()

    if concepto_tipo == "TRATO" or concepto_codigo == "TRATO":
        return app_root / TPL_TRATO_REL

    if concepto_tipo == "JORNADA_EXTRAORDINARIA":
        if concepto_codigo in {"SABADO", "SÁBADO"}:
            return app_root / TPL_SABADO_REL
        if concepto_codigo in {"HORAS_EXTRA", "HORA_EXTRA", "HORAS EXTRAS", "HORAS-EXTRA"}:
            return app_root / TPL_HORAS_EXTRA_REL

    # Default: BONO (incluye OTRO, BONO_PRODUCCION, BONO_ASISTENCIA, etc.)
    return app_root / TPL_BONO_REL


def _build_placeholders(item: ExtraRemuItem) -> dict[str, str]:
    t = getattr(item, "trabajador", None)
    cto = getattr(item, "contrato", None)
    obra = getattr(item, "obra", None) or (getattr(cto, "obra", None) if cto else None)
    emp = getattr(item, "empleador", None) or (getattr(cto, "empleador", None) if cto else None)
    lote = getattr(item, "lote", None)

    # -------------------------
    # Fechas / periodo
    # -------------------------
    hoy = date.today()
    anexo_fecha = fecha_larga_es(hoy)

    periodo_desde_val = getattr(item, "periodo_desde", None)
    periodo_hasta_val = getattr(item, "periodo_hasta", None)

    # Fallback: si no vienen en el item, usamos el mes del LOTE (requerimiento)
    if (periodo_desde_val is None or periodo_hasta_val is None) and lote is not None:
        anio = getattr(lote, "anio", None)
        mes = getattr(lote, "mes", None)
        if isinstance(anio, int) and isinstance(mes, int) and 1 <= mes <= 12:
            if periodo_desde_val is None:
                periodo_desde_val = date(anio, mes, 1)
            if periodo_hasta_val is None:
                periodo_hasta_val = _ultimo_dia_mes(anio, mes)

    # ✅ Para el texto del anexo queremos: "el 01 de febrero de 2026"
    periodo_desde = fecha_larga_el(periodo_desde_val)
    periodo_hasta = fecha_larga_el(periodo_hasta_val)

    # -------------------------
    # Conceptos / montos
    # -------------------------
    concepto_codigo_raw = (getattr(item, "concepto_codigo", "") or "").strip()
    concepto_tipo = (getattr(item, "concepto_tipo", "") or "").strip().upper()

    # ✅ “Se vea bonito”
    # - EXTRA_CONCEPTO: etiqueta humana (BONO/TRATO/SÁBADO/HORAS EXTRA)
    # - EXTRA_CODIGO: si es bono, mostrar "Bono desempeño" (bonito); si no, dejamos el código
    if concepto_tipo == "BONO":
        extra_concepto = "BONO"
        extra_codigo = _pretty_bono_codigo(concepto_codigo_raw) or "Bono"
    elif concepto_tipo == "TRATO":
        extra_concepto = "TRATO"
        extra_codigo = "TRATO"
    elif concepto_tipo == "JORNADA_EXTRAORDINARIA":
        # aquí concepto_codigo trae SABADO/HORAS_EXTRA
        ccu = concepto_codigo_raw.strip().upper()
        if ccu in {"SABADO", "SÁBADO"}:
            extra_concepto = "SÁBADO"
            extra_codigo = "SÁBADO"
        elif ccu in {"HORAS_EXTRA", "HORA_EXTRA", "HORAS EXTRAS", "HORAS-EXTRA"}:
            extra_concepto = "HORAS EXTRA"
            extra_codigo = "HORAS EXTRA"
        else:
            extra_concepto = "JORNADA EXTRAORDINARIA"
            extra_codigo = concepto_codigo_raw
    else:
        # fallback conservador
        extra_concepto = concepto_codigo_raw or "EXTRA"
        extra_codigo = concepto_codigo_raw or ""

    monto = getattr(item, "monto", None)
    resena = (getattr(item, "resena", "") or "").strip()

    # -------------------------
    # Rep legal
    # -------------------------
    rep_legal_nombre = (getattr(emp, "nombre_rep_legal", "") or "") if emp else ""
    rep_legal_rut_raw = (getattr(emp, "rut_rep_legal", "") or "") if emp else ""
    rep_legal_rut = rut_con_puntos(rep_legal_rut_raw) if rep_legal_rut_raw else ""

    # -------------------------
    # RUT trabajador (con puntos ✅)
    # -------------------------
    rut_trab = ""
    if t:
        rut_trab = rut_con_puntos(getattr(t, "rut_completo", None) or "")
        if not rut_trab:
            rut = (getattr(t, "rut", "") or "").strip()
            dv = (getattr(t, "dv", "") or "").strip()
            rut_trab = rut_con_puntos(f"{rut}-{dv}".strip("-"))

    placeholders = {
        "{{ANEXO_FECHA}}": anexo_fecha,

        # ✅ Extras “bonitos”
        "{{EXTRA_CONCEPTO}}": extra_concepto,
        "{{EXTRA_CODIGO}}": extra_codigo,
        "{{EXTRA_TIPO}}": (getattr(item, "concepto_tipo", "") or "").strip(),
        "{{EXTRA_PERIODO_DESDE}}": periodo_desde,
        "{{EXTRA_PERIODO_HASTA}}": periodo_hasta,
        "{{EXTRA_MONTO}}": _fmt_clp(monto),
        "{{EXTRA_MONTO_PALABRAS}}": clp_a_palabras(monto),
        "{{EXTRA_RESENA}}": resena,

        # TRATO (opcionales)
        "{{TRATO_UNIDADES}}": str(getattr(item, "unidades", "") or ""),
        "{{TRATO_VALOR_UNIDAD}}": _fmt_clp(getattr(item, "valor_unidad", None)) if getattr(item, "valor_unidad", None) else "",
        "{{TRATO_FORMULA}}": "",

        # Trabajador
        "{{TRABAJADOR_NOMBRES}}": (getattr(t, "nombres", "") or "") if t else "",
        "{{TRABAJADOR_AP_PATERNO}}": (getattr(t, "ap_paterno", "") or "") if t else "",
        "{{TRABAJADOR_AP_MATERNO}}": (getattr(t, "ap_materno", "") or "") if t else "",
        "{{TRABAJADOR_RUT}}": rut_trab,

        # Contrato
        "{{CONTRATO_FECHA_INGRESO}}": fecha_larga_es(getattr(cto, "fecha_inicio", None)) if cto else "",

        # Obra
        "{{OBRA_NOMBRE}}": (getattr(obra, "nombre", "") or "") if obra else "",
        "{{OBRA_DIRECCION}}": (getattr(obra, "direccion", "") or "") if obra else "",
        "{{OBRA_COMUNA}}": (getattr(obra, "comuna", "") or "") if obra else "",

        # Empleador
        "{{EMPLEADOR_RAZON_SOCIAL}}": (getattr(emp, "razon_social", "") or "") if emp else "",
        "{{EMPLEADOR_RUT}}": rut_con_puntos(getattr(emp, "rut", "") or "") if emp else "",
        "{{EMPLEADOR_DIRECCION}}": (getattr(emp, "direccion", "") or "") if emp else "",
        "{{EMPLEADOR_COMUNA}}": (getattr(emp, "comuna", "") or "") if emp else "",

        "{{REP_LEGAL_NOMBRE}}": rep_legal_nombre,
        "{{REP_LEGAL_RUT}}": rep_legal_rut,
    }

    # fórmula trato si hay datos
    unidades = getattr(item, "unidades", None)
    valor_unidad = getattr(item, "valor_unidad", None)
    if unidades is not None and valor_unidad is not None:
        placeholders["{{TRATO_FORMULA}}"] = f"{unidades} x {_fmt_clp(valor_unidad)}"

    return placeholders


def generar_docx_y_pdf_extra_item(item: ExtraRemuItem) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    """
    Genera DOCX/PDF para un ExtraRemuItem.
    Retorna:
      (docx_tmp_path, docx_nombre, pdf_tmp_path, pdf_nombre, docx_guardado_path, pdf_guardado_path)
    """
    if item is None:
        raise RuntimeError("Item inválido.")

    formato = (getattr(item, "formato", None) or "AMBOS").strip().upper()
    if formato not in ("DOCX", "PDF", "AMBOS"):
        formato = "AMBOS"

    t = getattr(item, "trabajador", None)
    if not t:
        raise RuntimeError("El ítem no tiene trabajador asociado.")

    # obra/centro_costo: preferimos item.centro_costo si existe, si no, inferimos por obra
    centro_costo = (getattr(item, "centro_costo", "") or "").strip()
    if not centro_costo:
        obra = getattr(item, "obra", None) or (getattr(getattr(item, "contrato", None), "obra", None))
        centro_costo = (getattr(obra, "centro_costo", "") or "").strip()
    if not centro_costo:
        raise RuntimeError("No se pudo determinar centro de costo (item/obra sin centro_costo).")

    # Plantilla
    tpl_path = _tpl_for_item(item)
    if not tpl_path.exists():
        raise FileNotFoundError(f"No existe plantilla: {tpl_path}")

    doc = DocxDocument(str(tpl_path))
    replace_placeholders(doc, _build_placeholders(item))

    # Naming corporativo
    concepto_codigo_raw = (getattr(item, "concepto_codigo", "") or "").strip()
    concepto_tipo = (getattr(item, "concepto_tipo", "") or "").strip().upper()

    if concepto_tipo == "BONO":
        concepto_label = _pretty_bono_codigo(concepto_codigo_raw) or "Bono"
    elif concepto_tipo == "TRATO":
        concepto_label = "Trato"
    elif concepto_tipo == "JORNADA_EXTRAORDINARIA":
        ccu = concepto_codigo_raw.strip().upper()
        if ccu in {"SABADO", "SÁBADO"}:
            concepto_label = "Sábado"
        elif ccu in {"HORAS_EXTRA", "HORA_EXTRA", "HORAS EXTRAS", "HORAS-EXTRA"}:
            concepto_label = "Horas extra"
        else:
            concepto_label = "Jornada extraordinaria"
    else:
        concepto_label = concepto_codigo_raw or "Extra"

    fecha_ref = getattr(item, "periodo_hasta", None) or getattr(item, "periodo_desde", None)
    if not fecha_ref:
        # fallback: si tampoco están en el item, usamos hoy (solo para nombre)
        fecha_ref = date.today()
    fecha_iso = fecha_ref.isoformat()

    nombre_trab = " ".join([p for p in [t.ap_paterno or "", t.ap_materno or "", t.nombres or ""] if p]).strip()
    base = _safe_filename(f"{fecha_iso} Anexo - {nombre_trab} ({concepto_label})")

    docx_name = f"{base}.docx"
    pdf_name = f"{base}.pdf"

    # tmp local (para descargas / staging)
    out_dir = Path("/tmp/rrhh_docs/extras")
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / docx_name
    doc.save(str(docx_path))

    pdf_path: Path | None = None
    if formato in ("PDF", "AMBOS"):
        pdf_tmp_dir = out_dir / "pdf"
        pdf_tmp_dir.mkdir(parents=True, exist_ok=True)
        pdf_tmp = convert_docx_to_pdf(docx_path, pdf_tmp_dir)
        pdf_tmp_path = Path(pdf_tmp) if isinstance(pdf_tmp, (str, Path)) else pdf_tmp
        pdf_path = out_dir / pdf_name
        if pdf_tmp_path != pdf_path:
            if pdf_path.exists():
                pdf_path.unlink()
            shutil.copy2(pdf_tmp_path, pdf_path)

    # Guardado Nextcloud
    nc = get_nc_paths()
    dest_dir = nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=t.nombres or "",
        ap_paterno=t.ap_paterno or "",
        ap_materno=t.ap_materno or "",
        tipo_doc="EXTRAS",
    )
    ensure_dir(dest_dir)

    docx_guardado = None
    pdf_guardado = None

    if formato in ("DOCX", "AMBOS"):
        dst_docx = dest_dir / docx_name
        shutil.copy2(docx_path, dst_docx)
        docx_guardado = str(dst_docx)

    if pdf_path is not None and formato in ("PDF", "AMBOS"):
        dst_pdf = dest_dir / pdf_name
        shutil.copy2(pdf_path, dst_pdf)
        pdf_guardado = str(dst_pdf)

    return (
        str(docx_path), docx_name,
        str(pdf_path) if pdf_path else None, (pdf_name if pdf_path else None),
        docx_guardado, pdf_guardado,
    )