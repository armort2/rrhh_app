"""
Servicios transversales para expediente documental laboral.

Objetivo Fase 1:
- Registrar documentos generados por el sistema en `documentos_laborales`.
- Evitar duplicados por contrato/tipo/ruta.
- Entregar un checklist simple para pantallas de contrato y futuras pantallas 360.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..extensions import db
from ..models import Contrato, DocumentoLaboral


@dataclass(frozen=True)
class DocumentChecklistItem:
    key: str
    label: str
    status: str
    detail: str
    severity: str = "info"

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "severity": self.severity,
        }


def _norm_extension(extension: str | None, ruta_archivo: str | None = None, nombre_archivo: str | None = None) -> str:
    ext = (extension or "").strip().lower().lstrip(".")
    if not ext:
        for source in (nombre_archivo, ruta_archivo):
            if source and "." in str(source):
                ext = str(source).rsplit(".", 1)[-1].lower().strip()
                break
    return ext if ext in {"pdf", "docx"} else "pdf"


def _nombre_desde_ruta(ruta_archivo: str | None) -> str | None:
    if not ruta_archivo:
        return None
    try:
        return Path(str(ruta_archivo)).name or None
    except Exception:
        return str(ruta_archivo).rstrip("/").rsplit("/", 1)[-1] or None


def register_generated_document(
    *,
    contrato: Contrato,
    tipo: str,
    ruta_archivo: str | Path | None,
    nombre_archivo: str | None = None,
    fecha_ref: date | None = None,
    extension: str | None = None,
    estado: str = "VIGENTE",
    commit: bool = False,
) -> DocumentoLaboral | None:
    """Registra un documento generado en el expediente del contrato.

    Si ya existe un registro con la misma `ruta_archivo`, se actualiza su nombre,
    tipo y estado. Esto permite regenerar sin llenar el expediente con duplicados.
    """
    if not contrato or not getattr(contrato, "id", None):
        raise ValueError("Se requiere un contrato persistido para registrar documentos.")

    ruta_txt = str(ruta_archivo).strip() if ruta_archivo else None
    nombre = (nombre_archivo or _nombre_desde_ruta(ruta_txt) or "").strip() or None
    tipo = (tipo or "").strip().upper()
    if not tipo:
        raise ValueError("Se requiere tipo documental para registrar el documento.")

    ext = _norm_extension(extension, ruta_txt, nombre)

    existente = None
    if ruta_txt:
        existente = DocumentoLaboral.query.filter_by(
            contrato_id=contrato.id,
            ruta_archivo=ruta_txt,
        ).first()

    if not existente and nombre:
        existente = DocumentoLaboral.query.filter_by(
            contrato_id=contrato.id,
            tipo=tipo,
            nombre_archivo=nombre,
        ).first()

    if existente:
        existente.tipo = tipo
        existente.ruta_archivo = ruta_txt
        existente.estado = estado or existente.estado or "VIGENTE"
        if nombre:
            existente.nombre_archivo = nombre
        doc = existente
    else:
        doc = DocumentoLaboral.crear_para_contrato(
            contrato=contrato,
            tipo=tipo,
            fecha_ref=fecha_ref,
            extension=ext,
            ruta_archivo=ruta_txt,
            estado=estado or "VIGENTE",
        )
        if nombre:
            doc.nombre_archivo = nombre
        db.session.add(doc)

    if commit:
        db.session.commit()

    return doc


def _has_doc_type(contrato: Contrato, tipo: str) -> bool:
    tipo = (tipo or "").upper()
    return any((getattr(doc, "tipo", "") or "").upper() == tipo for doc in getattr(contrato, "documentos", []) or [])


def build_contract_document_checklist(contrato: Contrato) -> dict[str, Any]:
    """Checklist operativo para generación/registro documental de un contrato."""
    trabajador = getattr(contrato, "trabajador", None)
    empleador = getattr(contrato, "empleador", None)
    obra = getattr(contrato, "obra", None)
    cargo = getattr(contrato, "cargo", None)
    horario = getattr(contrato, "horario", None)

    items: list[DocumentChecklistItem] = []

    items.append(DocumentChecklistItem(
        key="trabajador",
        label="Trabajador identificado",
        status="OK" if trabajador else "PENDIENTE",
        detail="Ficha asociada al contrato." if trabajador else "El contrato no tiene trabajador asociado.",
        severity="success" if trabajador else "danger",
    ))

    rut_ok = bool(trabajador and getattr(trabajador, "rut", None) and getattr(trabajador, "dv", None))
    items.append(DocumentChecklistItem(
        key="rut",
        label="RUT completo",
        status="OK" if rut_ok else "REVISAR",
        detail="RUT y dígito verificador disponibles." if rut_ok else "Falta RUT o dígito verificador en la ficha.",
        severity="success" if rut_ok else "warning",
    ))

    items.append(DocumentChecklistItem(
        key="empleador",
        label="Empleador asignado",
        status="OK" if empleador else "PENDIENTE",
        detail=getattr(empleador, "razon_social", None) or "Sin empleador asignado.",
        severity="success" if empleador else "danger",
    ))

    centro_costo = (getattr(obra, "centro_costo", "") or "").strip() if obra else ""
    items.append(DocumentChecklistItem(
        key="obra",
        label="Obra y centro de costo",
        status="OK" if obra and centro_costo else "REVISAR",
        detail=(f"{getattr(obra, 'nombre', '')} · CC {centro_costo}" if obra and centro_costo else "Falta obra o centro de costo para archivar en Nextcloud."),
        severity="success" if obra and centro_costo else "warning",
    ))

    items.append(DocumentChecklistItem(
        key="cargo",
        label="Cargo contractual",
        status="OK" if cargo else "PENDIENTE",
        detail=getattr(cargo, "nombre", None) or "Sin cargo asociado.",
        severity="success" if cargo else "danger",
    ))

    jornada_ok = bool((getattr(contrato, "jornada", "") or "").strip() or (horario and getattr(horario, "descripcion", None)))
    items.append(DocumentChecklistItem(
        key="jornada",
        label="Jornada / horario",
        status="OK" if jornada_ok else "REVISAR",
        detail="Existe texto de jornada u horario de catálogo." if jornada_ok else "Falta texto de jornada para la plantilla.",
        severity="success" if jornada_ok else "warning",
    ))

    sueldo_ok = getattr(contrato, "sueldo_base", None) is not None
    items.append(DocumentChecklistItem(
        key="sueldo",
        label="Remuneración base",
        status="OK" if sueldo_ok else "REVISAR",
        detail="Sueldo base informado." if sueldo_ok else "Falta sueldo base.",
        severity="success" if sueldo_ok else "warning",
    ))

    contrato_doc_ok = _has_doc_type(contrato, "CONTRATOS")
    items.append(DocumentChecklistItem(
        key="documento_contrato",
        label="Contrato registrado en expediente",
        status="OK" if contrato_doc_ok else "PENDIENTE",
        detail="Ya existe documento tipo CONTRATOS." if contrato_doc_ok else "Aún no hay documento tipo CONTRATOS registrado.",
        severity="success" if contrato_doc_ok else "info",
    ))

    counts = {"OK": 0, "REVISAR": 0, "PENDIENTE": 0}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1

    bloqueantes = [item.as_dict() for item in items if item.severity == "danger"]
    advertencias = [item.as_dict() for item in items if item.severity == "warning"]

    return {
        "items": [item.as_dict() for item in items],
        "counts": counts,
        "bloqueantes": bloqueantes,
        "advertencias": advertencias,
        "puede_generar": not bloqueantes,
    }
