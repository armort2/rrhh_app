from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from flask import current_app
from docx import Document as DocxDocument

from app.models import TipoAcuerdoPago
from .docx_engine import replace_placeholders
from .paths_nextcloud import get_nc_paths

if TYPE_CHECKING:
    from app.models import AcuerdoPago


# ✅ Plantilla
TEMPLATE_REL_PATH = "document_templates/solicitudes/acuerdo_de_pago.docx"


# =========================
# Labels + textos
# =========================
TIPO_ACUERDO_LABELS = {
    TipoAcuerdoPago.DINERO: "Préstamo en dinero",
    TipoAcuerdoPago.HERRAMIENTAS: "Entrega de herramientas",
    TipoAcuerdoPago.EPP_DIFERENCIA: "Diferencia por EPP mejorado",
    TipoAcuerdoPago.EXTRAVIO_EQUIPOS: "Descuento por extravío de herramientas y/o equipos",
    TipoAcuerdoPago.OTROS: "Otros",
}

MODALIDAD_ACUERDO_LABELS = {
    "DESCUENTO_LIQUIDACION": "Descuento por liquidación",
}

TEXTO_ACUERDO_DINERO_V2 = (
    "El Trabajador declara haber recibido del Empleador, en calidad de préstamo de dinero, "
    "la suma total de ${ACUERDO_MONTO} ({ACUERDO_MONTO_PALABRAS} pesos), monto que se obliga "
    "a restituir en la forma y condiciones establecidas en el presente acuerdo, beneficio cuyo "
    "origen corresponde a {ACUERDO_CONCEPTO}."
)

TEXTO_ACUERDO_HERRAMIENTAS_V2 = (
    "El Trabajador declara haber recibido del Empleador, en este acto, herramientas de trabajo "
    "adquiridas por la empresa y entregadas para su uso personal, cuyo valor total asciende a "
    "${ACUERDO_MONTO} ({ACUERDO_MONTO_PALABRAS} pesos), monto que el Trabajador se obliga a "
    "restituir al Empleador en la forma y condiciones establecidas en el presente acuerdo. "
    "Las herramientas entregadas corresponden a {ACUERDO_CONCEPTO}, las cuales han sido recibidas "
    "en conformidad por el Trabajador, quien declara conocer su valorización y estado."
)

TEXTO_ACUERDO_EPP_DIFERENCIA_V2 = (
    "El Trabajador declara haber solicitado voluntariamente la entrega de elementos de protección personal "
    "de características superiores a aquellos que el Empleador proporciona regularmente conforme a la normativa "
    "vigente, aceptando expresamente asumir el pago de la diferencia de costo entre el equipamiento estándar y el "
    "equipamiento mejorado, diferencia que asciende a ${ACUERDO_MONTO} ({ACUERDO_MONTO_PALABRAS} pesos). "
    "La diferencia de costo indicada corresponde a {ACUERDO_CONCEPTO}, declaración que el Trabajador formula "
    "en pleno conocimiento de que el Empleador cumple con la entrega de EPP obligatorios, siendo esta mejora "
    "una solicitud personal y voluntaria del Trabajador."
)

TEXTO_ACUERDO_EXTRAVIO_EQUIPOS_V2 = (
    "El Trabajador declara que, con ocasión de sus funciones, extravió y/o no restituyó "
    "herramientas y/o equipos de propiedad del Empleador, cuyo detalle corresponde a {ACUERDO_CONCEPTO}, "
    "reconociendo su valorización y autorizando expresamente al Empleador para descontar de su liquidación "
    "de remuneraciones y/o finiquito la suma total de ${ACUERDO_MONTO} ({ACUERDO_MONTO_PALABRAS} pesos), "
    "en la forma y condiciones señaladas en el presente acuerdo."
)

TEXTO_ACUERDO_OTROS_V2 = (
    "El Trabajador reconoce y acepta la obligación indicada en el presente acuerdo, cuyo origen corresponde a "
    "{ACUERDO_CONCEPTO}, autorizando expresamente al Empleador para efectuar el descuento por la suma total de "
    "${ACUERDO_MONTO} ({ACUERDO_MONTO_PALABRAS} pesos), en la forma y condiciones aquí establecidas."
)


ACUERDO_RECONOCIMIENTO_TEXTO_MAP_V2 = {
    TipoAcuerdoPago.DINERO: TEXTO_ACUERDO_DINERO_V2,
    TipoAcuerdoPago.HERRAMIENTAS: TEXTO_ACUERDO_HERRAMIENTAS_V2,
    TipoAcuerdoPago.EPP_DIFERENCIA: TEXTO_ACUERDO_EPP_DIFERENCIA_V2,
    TipoAcuerdoPago.EXTRAVIO_EQUIPOS: TEXTO_ACUERDO_EXTRAVIO_EQUIPOS_V2,
    TipoAcuerdoPago.OTROS: TEXTO_ACUERDO_OTROS_V2,
}


def acuerdo_pago_texto_reconocimiento_v2(
    acuerdo: AcuerdoPago,
    monto_str: str,
    monto_palabras: str,
) -> str:
    if not acuerdo or not acuerdo.tipo:
        return ""

    template = ACUERDO_RECONOCIMIENTO_TEXTO_MAP_V2.get(acuerdo.tipo)
    if not template:
        return ""

    concepto = (acuerdo.concepto or "").strip()
    return template.format(
        ACUERDO_MONTO=monto_str,
        ACUERDO_MONTO_PALABRAS=monto_palabras,
        ACUERDO_CONCEPTO=concepto,
    )


def validar_acuerdo_pago(acuerdo: AcuerdoPago) -> list[str]:
    errs: list[str] = []
    if not acuerdo:
        return ["Acuerdo inválido."]

    if not acuerdo.trabajador_id:
        errs.append("Debe seleccionar un trabajador.")

    if not acuerdo.tipo:
        errs.append("Debe seleccionar el tipo de acuerdo.")

    concepto = (acuerdo.concepto or "").strip()
    if not concepto:
        errs.append("Debe indicar el concepto del acuerdo (motivo).")

    try:
        mt = float(acuerdo.monto_total or 0)
    except Exception:
        mt = -1

    if mt <= 0:
        errs.append("El monto total debe ser mayor a 0.")

    if not acuerdo.cuotas or int(acuerdo.cuotas) < 1:
        errs.append("La cantidad de cuotas debe ser 1 o más.")

    if (acuerdo.modalidad or "").strip().upper() != "DESCUENTO_LIQUIDACION":
        errs.append("Modalidad inválida.")

    if acuerdo.tipo == TipoAcuerdoPago.EPP_DIFERENCIA:
        voluntario = False
        if isinstance(acuerdo.meta, dict):
            voluntario = bool(acuerdo.meta.get("epp_mejora_voluntaria"))
        if not voluntario:
            errs.append("Para EPP mejorado, debe quedar registrada la confirmación de solicitud voluntaria.")

    return errs


# =========================
# Helpers formato
# =========================
def _fmt_fecha_es(d: date) -> str:
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"

def _fmt_mes_inicio_es(ym: str | None) -> str:
    """
    Convierte 'YYYY-MM' -> 'febrero de 2026'
    Si viene vacío o inválido, retorna ''.
    """
    s = (ym or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if not m:
        return s  # fallback: dejamos lo que venga (mejor que romper)
    year = int(m.group(1))
    month = int(m.group(2))
    if month < 1 or month > 12:
        return s

    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{meses[month - 1]} de {year}"

def _fmt_clp(v: Decimal | float | int | str | None) -> str:
    """
    Retorna monto con separador CL, SIN símbolo "$".
    Ej: 250000 -> "250.000"
    """
    if v is None:
        n = 0
    else:
        try:
            n = int(Decimal(str(v)))
        except Exception:
            n = 0
    return f"{n:,}".replace(",", ".")


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
            body, dv2 = s2, ""
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
    return out or "ACUERDO_PAGO"


def _docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
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

    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError("La conversión a PDF terminó sin error, pero no se encontró el PDF generado.")
    return pdf_path


def _guardar_en_carpeta_trabajador_acuerdo_pago(
    acuerdo: AcuerdoPago,
    docx_path: Path,
    pdf_path: Path | None,
) -> tuple[str | None, str | None]:
    """
    Copia a:
      /<CENTRO_DE_COSTO>/Laboral/Trabajadores/<Ap Pat> <Ap Mat> <Nombres>/ACUERDOS DE PAGO/
    """
    if acuerdo.trabajador_id is None or getattr(acuerdo, "trabajador", None) is None:
        return (None, None)

    t = acuerdo.trabajador

    centro_costo = ""
    if getattr(acuerdo, "obra", None) is not None:
        centro_costo = (getattr(acuerdo.obra, "centro_costo", "") or "").strip()
    if not centro_costo:
        centro_costo = "SIN_NOMBRE"

    nc = get_nc_paths()

    # ✅ Carpeta bonita:
    # Si por algún motivo tu builder no tolera espacios, cambia por: "ACUERDOS"
    destino_dir = nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=(t.nombres or ""),
        ap_paterno=(t.ap_paterno or ""),
        ap_materno=(t.ap_materno or ""),
        tipo_doc="ACUERDOS DE PAGO",
    )

    destino_dir.mkdir(parents=True, exist_ok=True)

    dst_docx = destino_dir / docx_path.name
    shutil.copy2(docx_path, dst_docx)

    dst_pdf = None
    if pdf_path is not None:
        dst_pdf = destino_dir / pdf_path.name
        shutil.copy2(pdf_path, dst_pdf)

    return (str(dst_docx), str(dst_pdf) if dst_pdf else None)


# =========================
# Placeholders
# =========================
def build_placeholders_acuerdo_pago_v2(
    acuerdo: AcuerdoPago,
    *,
    monto_str: str,
    monto_palabras: str,
    monto_cuota_str: str,
    texto_reconocimiento: str,
) -> dict[str, str]:
    t = getattr(acuerdo, "trabajador", None)
    o = getattr(acuerdo, "obra", None)
    e = getattr(acuerdo, "empleador", None) or (getattr(t, "empleador_preferente", None) if t else None)

    trab_nombres = (getattr(t, "nombres", "") or "").strip() if t else ""
    trab_ap_pat = (getattr(t, "ap_paterno", "") or "").strip() if t else ""
    trab_ap_mat = (getattr(t, "ap_materno", "") or "").strip() if t else ""

    obra_nombre = (getattr(o, "nombre", "") or "").strip() if o else ""
    obra_comuna = (getattr(o, "comuna", "") or "").strip() if o else ""
    obra_direccion = (getattr(o, "direccion", "") or "").strip() if o else ""

    emp_razon = (getattr(e, "razon_social", "") or "").strip() if e else ""

    emp_rut_fmt = ""
    if e:
        emp_rut_fmt = _fmt_rut_cl(getattr(e, "rut", None), getattr(e, "dv", None))

    trab_rut_fmt = ""
    if t:
        rut_comp = getattr(t, "rut_completo", None)
        if rut_comp:
            trab_rut_fmt = _fmt_rut_cl(rut_comp, None)
        else:
            trab_rut_fmt = _fmt_rut_cl(getattr(t, "rut", None), getattr(t, "dv", None))

    fecha_ac = acuerdo.fecha_acuerdo or date.today()

    return {
        "EMPLEADOR_RAZON_SOCIAL": emp_razon,
        "EMPLEADOR_RUT": emp_rut_fmt,
        "OBRA_NOMBRE": obra_nombre,
        "OBRA_COMUNA": obra_comuna,
        "OBRA_DIRECCION": obra_direccion,

        "ACUERDO_N": str(acuerdo.numero or ""),
        "ACUERDO_FECHA": _fmt_fecha_es(fecha_ac),
        "ACUERDO_CONCEPTO": (acuerdo.concepto or "").strip(),

        "ACUERDO_MONTO": monto_str,
        "ACUERDO_MONTO_PALABRAS": monto_palabras,
        "ACUERDO_CUOTAS": str(acuerdo.cuotas or ""),
        "ACUERDO_MONTO_CUOTA": monto_cuota_str,
        "ACUERDO_MES_INICIO_DESCUENTO": _fmt_mes_inicio_es(acuerdo.mes_inicio_descuento),

        "ACUERDO_RECONOCIMIENTO_TEXTO": texto_reconocimiento,

        "TRABAJADOR_NOMBRES": trab_nombres,
        "TRABAJADOR_AP_PATERNO": trab_ap_pat,
        "TRABAJADOR_AP_MATERNO": trab_ap_mat,
        "TRABAJADOR_RUT": trab_rut_fmt,
    }


# =========================
# Generación DOCX + PDF
# =========================
def generar_docx_y_pdf_acuerdo_pago(acuerdo: AcuerdoPago) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    """
    Genera DOCX desde plantilla, genera PDF y guarda copia en carpeta del trabajador.
    Retorna:
      (docx_tmp_path, docx_nombre, pdf_tmp_path, pdf_nombre, docx_guardado_path, pdf_guardado_path)
    """
    app_root = Path(current_app.root_path)  # web/app
    tpl_path = app_root / TEMPLATE_REL_PATH
    if not tpl_path.exists():
        raise FileNotFoundError(f"No existe plantilla: {tpl_path}")

    doc = DocxDocument(str(tpl_path))

    try:
        total_int = int(Decimal(str(acuerdo.monto_total or 0)))
    except Exception:
        total_int = 0

    try:
        cuota_int = int(Decimal(str(acuerdo.monto_cuota or 0)))
    except Exception:
        cuota_int = 0

    monto_str = _fmt_clp(total_int)
    monto_cuota_str = _fmt_clp(cuota_int)
    monto_palabras = (numero_a_palabras_cl(total_int)).upper()

    texto_recon = acuerdo_pago_texto_reconocimiento_v2(
        acuerdo,
        monto_str=monto_str,
        monto_palabras=monto_palabras,
    )

    placeholders = build_placeholders_acuerdo_pago_v2(
        acuerdo,
        monto_str=monto_str,
        monto_palabras=monto_palabras,
        monto_cuota_str=monto_cuota_str,
        texto_reconocimiento=texto_recon,
    )

    replace_placeholders(doc, placeholders)

    fecha_iso = (acuerdo.fecha_acuerdo or date.today()).isoformat()

    t = getattr(acuerdo, "trabajador", None)
    if t is not None:
        full_name = " ".join(
            p for p in [
                getattr(t, "ap_paterno", "") or "",
                getattr(t, "ap_materno", "") or "",
                getattr(t, "nombres", "") or "",
            ]
            if p
        ).strip()
    else:
        full_name = "Trabajador"

    full_name = _safe_filename(full_name)

    docx_name = re.sub(r"\s+", " ", f"{fecha_iso} Acuerdo de Pago - {full_name}.docx").strip()
    pdf_name = re.sub(r"\s+", " ", f"{fecha_iso} Acuerdo de Pago - {full_name}.pdf").strip()

    out_dir = Path("/tmp/rrhh_docs/acuerdos_pago")
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / docx_name
    doc.save(str(docx_path))

    pdf_tmp_path = _docx_to_pdf(docx_path, out_dir)

    pdf_path = out_dir / pdf_name
    if pdf_tmp_path != pdf_path:
        try:
            if pdf_path.exists():
                pdf_path.unlink()
            pdf_tmp_path.rename(pdf_path)
        except Exception:
            shutil.copy2(pdf_tmp_path, pdf_path)

    docx_guardado, pdf_guardado = _guardar_en_carpeta_trabajador_acuerdo_pago(acuerdo, docx_path, pdf_path)

    return (
        str(docx_path), docx_name,
        str(pdf_path), pdf_name,
        docx_guardado, pdf_guardado,
    )


def generar_docx_acuerdo_pago(acuerdo: AcuerdoPago) -> tuple[str, str]:
    docx_path, docx_name, _, _, _, _ = generar_docx_y_pdf_acuerdo_pago(acuerdo)
    return docx_path, docx_name