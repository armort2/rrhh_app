# web/app/services/anexos_extension_service.py
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from flask import current_app

from ..config import generar_nombre_documento
from ..extensions import db
from ..models import AnexoExtensionContrato, Contrato, EventoLaboral
from ..services.docx_engine import replace_placeholders
from ..services.paths_nextcloud import get_nc_paths
from ..services.pdf_convert import convert_docx_to_pdf
from ..services.storage_nextcloud_fs import ensure_dir
from ..templates.utils.dates import fecha_larga_es

from docx import Document


def _build_docx(template_path: Path, variables: dict[str, str], output_path: Path) -> Path:
    doc = Document(str(template_path))
    replace_placeholders(doc, variables)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def generar_anexo_extension(
    *,
    contrato: Contrato,
    fecha_anexo: date,
    nueva_fecha_termino: date,
    observaciones: str | None,
    formato: str,  # "docx" | "pdf" | "ambos"
    creado_por: int | None = None,
) -> AnexoExtensionContrato:
    """
    Genera Anexo de Extensión:
    - Valida insumos mínimos (contrato con trabajador/empleador)
    - Genera DOCX/PDF según formato
    - Guarda en Nextcloud (FS mount)
    - Inserta registro en anexos_extension_contrato
    - Inserta EventoLaboral (recomendado)
    - Actualiza contrato.fecha_termino
    """
    if not contrato.trabajador:
        raise ValueError("Contrato sin trabajador asociado.")
    if not contrato.empleador:
        raise ValueError("Contrato sin empleador asociado.")

    trabajador = contrato.trabajador
    empleador = contrato.empleador
    obra = contrato.obra

    anterior = getattr(contrato, "fecha_termino", None)
    if anterior and nueva_fecha_termino <= anterior:
        raise ValueError("La nueva fecha debe ser posterior a la fecha de término anterior.")

    formato = (formato or "ambos").lower()
    if formato not in ("docx", "pdf", "ambos"):
        formato = "ambos"

    # Plantilla DOCX
    templates_root = Path(current_app.root_path) / "document_templates" / "anexos"
    tpl = templates_root / "anexo_extension_contrato.docx"
    if not tpl.exists():
        raise FileNotFoundError("No se encontró anexo_extension_contrato.docx en document_templates/anexos.")

    # Variables para la plantilla
    variables = {
        "{{OBRA_COMUNA}}": obra.comuna if obra else "",
        "{{ANEXO_FECHA}}": fecha_larga_es(fecha_anexo),

        "{{EMPLEADOR_RAZON_SOCIAL}}": empleador.razon_social or "",
        "{{EMPLEADOR_RUT}}": (getattr(empleador, "rut", "") or ""),
        "{{REP_LEGAL_NOMBRE}}": (getattr(empleador, "nombre_rep_legal", "") or ""),
        "{{REP_LEGAL_RUT}}": (getattr(empleador, "rut_rep_legal", "") or ""),
        "{{EMPLEADOR_DIRECCION}}": empleador.direccion or "",
        "{{EMPLEADOR_COMUNA}}": empleador.comuna or "",

        "{{TRABAJADOR_NOMBRES}}": trabajador.nombres or "",
        "{{TRABAJADOR_AP_PATERNO}}": trabajador.ap_paterno or "",
        "{{TRABAJADOR_AP_MATERNO}}": trabajador.ap_materno or "",
        "{{TRABAJADOR_RUT}}": (getattr(trabajador, "rut", "") or ""),

        "{{CONTRATO_FECHA_INICIO}}": fecha_larga_es(contrato.fecha_inicio),
        "{{CONTRATO_FECHA_TERMINO_ANTERIOR}}": fecha_larga_es(anterior),
        "{{CONTRATO_FECHA_TERMINO_NUEVA}}": fecha_larga_es(nueva_fecha_termino),

        "{{CARGO_NOMBRE}}": contrato.cargo.nombre if contrato.cargo else "",
        "{{ANEXO_OBSERVACIONES}}": observaciones or "",
    }

    # Carpeta destino Nextcloud
    nc = get_nc_paths()
    dest_dir = nc.dir_trabajador(
        empleador_razon_social=empleador.razon_social,
        rut=(getattr(trabajador, "rut", "") or ""),
        dv=(getattr(trabajador, "dv", "") or ""),
        nombres=trabajador.nombres,
        ap_paterno=trabajador.ap_paterno,
        ap_materno=trabajador.ap_materno,
        tipo_doc="ANEXOS",
    )

    out_tmp = Path(current_app.instance_path) / "generated_docs"
    ensure_dir(out_tmp)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    docx_tmp = out_tmp / f"tmp_anexo_extension_{contrato.id}_{stamp}.docx"
    pdf_tmp_dir = out_tmp / "pdf"
    ensure_dir(pdf_tmp_dir)

    ensure_dir(dest_dir)

    # Nombres finales
    nombre_docx = generar_nombre_documento(
        tipo="ANEXO_EXTENSION_CONTRATO",
        ap_paterno=trabajador.ap_paterno or "SIN_APELLIDO",
        fecha_ref=fecha_anexo,
        extension="docx",
    )
    docx_final = dest_dir / nombre_docx

    nombre_pdf = generar_nombre_documento(
        tipo="ANEXO_EXTENSION_CONTRATO",
        ap_paterno=trabajador.ap_paterno or "SIN_APELLIDO",
        fecha_ref=fecha_anexo,
        extension="pdf",
    )
    pdf_final = dest_dir / nombre_pdf

    # 1) Generar DOCX temporal
    _build_docx(tpl, variables, docx_tmp)

    # 2) Copiar DOCX final si corresponde
    if formato in ("docx", "ambos", "pdf"):
        docx_final.write_bytes(docx_tmp.read_bytes())

    # 3) PDF si corresponde
    pdf_generado = False
    if formato in ("pdf", "ambos"):
        pdf_tmp = convert_docx_to_pdf(docx_tmp, pdf_tmp_dir)
        pdf_final.write_bytes(pdf_tmp.read_bytes())
        pdf_generado = True

    # 4) Insert BD: AnexoExtensionContrato
    anexo = AnexoExtensionContrato(
        contrato_id=contrato.id,
        trabajador_id=trabajador.id,
        empleador_id=contrato.empleador_id,
        obra_id=contrato.obra_id,
        fecha_anexo=fecha_anexo,
        fecha_termino_anterior=anterior,
        fecha_termino_nueva=nueva_fecha_termino,
        observaciones=observaciones,
        formato=formato.upper(),
        estado="VIGENTE",
        docx_nombre=nombre_docx if formato in ("docx", "ambos", "pdf") else None,
        docx_ruta=str(docx_final) if formato in ("docx", "ambos", "pdf") else None,
        pdf_nombre=nombre_pdf if pdf_generado else None,
        pdf_ruta=str(pdf_final) if pdf_generado else None,
        meta={
            "tipo": "EXTENSION_CONTRATO",
            "creado_por": creado_por,
        },
    )

    # 5) EventoLaboral (expediente recomendado)
    evento = EventoLaboral(
        trabajador_id=trabajador.id,
        contrato_id=contrato.id,
        obra_id=contrato.obra_id,
        empleador_id=contrato.empleador_id,
        categoria="ANEXO",
        tipo="EXTENSION_CONTRATO",
        titulo=f"Anexo extensión contrato (Contrato #{contrato.id})",
        fecha_evento=fecha_anexo,
        estado="VIGENTE",
        nombre_archivo=(nombre_pdf if pdf_generado else nombre_docx),
        ruta_archivo=(str(pdf_final) if pdf_generado else str(docx_final)),
        meta={
            "anexo_extension_id": None,  # se setea si quieres luego de flush
            "fecha_termino_anterior": str(anterior) if anterior else None,
            "fecha_termino_nueva": str(nueva_fecha_termino),
            "formato": formato,
        },
    )

    # 6) Actualizar contrato
    contrato.fecha_termino = nueva_fecha_termino

    # Persistencia
    db.session.add(anexo)
    db.session.add(evento)
    db.session.add(contrato)

    # Si quieres enlazar evento.meta con anexo.id:
    db.session.flush()
    evento.meta = {**(evento.meta or {}), "anexo_extension_id": anexo.id}

    return anexo
