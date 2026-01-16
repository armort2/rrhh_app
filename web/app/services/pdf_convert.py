from __future__ import annotations

import subprocess
from pathlib import Path


def convert_docx_to_pdf(docx_path: Path, pdf_out_dir: Path) -> Path:
    """
    Convierte DOCX -> PDF usando LibreOffice headless.
    Requiere paquete 'libreoffice' instalado en el host/container.
    """
    pdf_out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "soffice",
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_out_dir),
        str(docx_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Error convirtiendo a PDF con LibreOffice.\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    pdf_path = pdf_out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError("LibreOffice terminó sin error, pero el PDF no apareció en el directorio de salida.")
    return pdf_path
