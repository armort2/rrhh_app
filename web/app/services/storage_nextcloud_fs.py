from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> None:
    """
    Crea directorios si no existen (equivalente a mkdir -p).
    Lanza excepción si no se puede crear por permisos o si el mount no está disponible.
    """
    path.mkdir(parents=True, exist_ok=True)


def safe_write_bytes(path: Path, data: bytes) -> None:
    """
    Escritura atómica simple:
    - Escribe a .tmp
    - Reemplaza al final
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
