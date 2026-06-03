# web/app/services/storage_nextcloud_fs.py
from __future__ import annotations

from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def ensure_dir(path: PathLike) -> Path:
    """
    Crea directorios si no existen (equivalente a mkdir -p).
    Acepta Path o str y retorna Path normalizado.
    """
    p = path if isinstance(path, Path) else Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_write_bytes(path: PathLike, data: bytes) -> None:
    """
    Escritura atómica simple:
    - Escribe a .tmp
    - Reemplaza al final
    """
    p = path if isinstance(path, Path) else Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
