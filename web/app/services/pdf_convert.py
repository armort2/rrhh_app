# web/app/services/pdf_convert.py
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from shutil import which


def _find_lo_exec() -> str:
    exe = which("soffice") or which("libreoffice")
    if not exe:
        raise RuntimeError(
            "No se encontró LibreOffice en el sistema (faltan 'soffice'/'libreoffice'). "
            "Instala libreoffice en el contenedor/host para habilitar conversión PDF."
        )
    return exe


def convert_docx_to_pdf(docx_path: str | Path, pdf_out: str | Path) -> Path:
    """
    Convierte DOCX a PDF con LibreOffice.

    pdf_out puede ser:
      - un DIRECTORIO de salida (modo legacy): /ruta/salida/
      - un ARCHIVO .pdf específico: /ruta/salida/mi_archivo.pdf

    Retorna la ruta final del PDF.
    """
    docx_path = Path(docx_path)

    out = Path(pdf_out)

    # Caso A: me pasaron un archivo .pdf
    if out.suffix.lower() == ".pdf":
        pdf_out_dir = out.parent
        target_pdf = out
    else:
        # Caso B: me pasaron un directorio (legacy)
        pdf_out_dir = out
        target_pdf = pdf_out_dir / (docx_path.stem + ".pdf")

    pdf_out_dir.mkdir(parents=True, exist_ok=True)

    lo = _find_lo_exec()

    # LibreOffice puede quedar colgado si reutiliza un perfil bloqueado o corrupto.
    # Usamos un perfil temporal aislado por conversión y timeout explícito para no
    # matar el worker de Gunicorn por espera infinita.
    timeout_seconds = int(os.environ.get("LIBREOFFICE_CONVERT_TIMEOUT", "60"))

    with tempfile.TemporaryDirectory(prefix="lo-profile-") as lo_profile:
        profile_uri = Path(lo_profile).resolve().as_uri()
        cmd = [
            lo,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_out_dir),
            str(docx_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "LibreOffice excedió el tiempo máximo de conversión a PDF.\n"
                f"Timeout: {timeout_seconds} segundos\n"
                f"Archivo: {docx_path}"
            ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            "Error convirtiendo a PDF con LibreOffice.\n"
            f"CMD: {' '.join(cmd)}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    generated_pdf = pdf_out_dir / (docx_path.stem + ".pdf")
    if not generated_pdf.exists():
        raise RuntimeError(
            "LibreOffice terminó sin error, pero el PDF no apareció en el directorio de salida.\n"
            f"Esperado: {generated_pdf}"
        )

    # Si el usuario pidió un nombre específico, renombramos/movemos al target.
    if generated_pdf != target_pdf:
        try:
            target_pdf.unlink(missing_ok=True)  # por si existía
        except Exception:
            # si no se puede borrar, igual intentamos reemplazar
            pass
        generated_pdf.replace(target_pdf)

    if not target_pdf.exists():
        raise RuntimeError(
            "La conversión finalizó, pero no se encontró el PDF final.\n"
            f"Final: {target_pdf}"
        )

    return target_pdf
