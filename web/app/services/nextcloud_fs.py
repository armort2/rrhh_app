from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(frozen=True)
class NextcloudFSConfig:
    root_dir: Path  # ej: /mnt/nextcloud/DOCUMENTACION LABORAL


def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_to_nextcloud(
    cfg: NextcloudFSConfig,
    relative_dir: str,
    local_file: Path,
    filename: str | None = None,
) -> str:
    """
    Copia un archivo a la estructura Nextcloud en el servidor.
    - cfg.root_dir: carpeta base local sincronizada/montada
    - relative_dir: ruta relativa bajo root_dir (ej: EMPLEADORES/.../CONTRATOS)
    Retorna la ruta final relativa (para guardar en DB).
    """
    if not local_file.exists():
        raise FileNotFoundError(f"No existe el archivo local: {local_file}")

    filename = filename or local_file.name

    # Normaliza y arma destino
    rel = Path(relative_dir.strip("/"))
    dest_dir = cfg.root_dir / rel
    safe_mkdir(dest_dir)

    dest_path = dest_dir / filename

    # Copia conservadora (preserva metadata)
    shutil.copy2(local_file, dest_path)

    # Retornamos la ruta lógica relativa (como la verías en Nextcloud)
    return str(Path(cfg.root_dir.name) / rel / filename)
