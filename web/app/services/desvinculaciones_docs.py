from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from flask import current_app

from ..models import Desvinculacion, Trabajador, Contrato
from ..templates.utils.dates import fecha_larga_es
from ..services.docx_engine import build_contract_docx  # reutilizamos engine
from ..services.pdf_convert import convert_docx_to_pdf


@dataclass(frozen=True)
class DesvDocsResult:
    docx_path: Path
    pdf_path: Path
    docx_name: str
    pdf_name: str


def _fmt(d: date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def _base_context(desv: Desvinculacion) -> dict:
    """
    Contexto base para plantillas DOCX (carta/finiquito).
    Mantén nombres estables. Luego ampliamos (remuneraciones, feriado proporcional, etc.)
    """
    t: Trabajador = desv.trabajador
    c: Contrato = desv.contrato
    causal = desv.causal

    return {
        # Identidad
        "trabajador_nombres": f"{t.nombres} {t.ap_paterno} {t.ap_materno}",
        "trabajador_rut": getattr(t, "rut_completo", None) or f"{t.rut}-{t.dv}",
        "trabajador_direccion": (t.direccion or ""),
        "trabajador_comuna": (t.comuna or ""),

        # Contrato / Empresa / Obra
        "contrato_id": c.id,
        "empleador_id": getattr(c, "empleador_id", None),
        "obra_id": getattr(c, "obra_id", None),

        # Causal
        "causal_resumida": getattr(causal, "causal_resumida", "") if causal else "",
        "causal_finiquito": getattr(causal, "causal_finiquito", "") if causal else "",

        # Fechas claves
        "fecha_termino": _fmt(desv.fecha_termino),
        "fecha_termino_larga": fecha_larga_es(desv.fecha_termino) if getattr(desv, "fecha_termino", None) else "",
        "fecha_aviso": _fmt(desv.fecha_aviso),
        "fecha_aviso_larga": fecha_larga_es(desv.fecha_aviso) if getattr(desv, "fecha_aviso", None) else "",

        # Detalle libre
        "motivo_detalle": (desv.motivo_detalle or ""),
    }


def build_carta_aviso_docx(desv: Desvinculacion, out_docx: Path) -> None:
    """
    Genera DOCX de carta aviso.
    Reutiliza build_contract_docx como motor de render con plantilla y contexto.
    """
    template = current_app.config.get("TEMPLATE_CARTA_AVISO_DOCX")
    if not template:
        raise RuntimeError("Falta config TEMPLATE_CARTA_AVISO_DOCX en config.py")

    ctx = _base_context(desv)
    # Puedes agregar más campos de carta aquí en el futuro
    build_contract_docx(template_path=Path(template), context=ctx, output_path=out_docx)


def build_finiquito_docx(desv: Desvinculacion, out_docx: Path) -> None:
    """
    Genera DOCX de finiquito (MVP).
    """
    template = current_app.config.get("TEMPLATE_FINIQUITO_DOCX")
    if not template:
        raise RuntimeError("Falta config TEMPLATE_FINIQUITO_DOCX en config.py")

    ctx = _base_context(desv)
    # Luego agregamos montos, feriado proporcional, indemnizaciones, etc.
    build_contract_docx(template_path=Path(template), context=ctx, output_path=out_docx)


def make_pdf_from_docx(docx_path: Path, pdf_path: Path) -> None:
    """
    Wrapper para consistencia.
    """
    convert_docx_to_pdf(str(docx_path), str(pdf_path))
