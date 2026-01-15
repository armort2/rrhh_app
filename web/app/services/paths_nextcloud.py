# web/app/services/paths_nextcloud.py

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import NEXTCLOUD_MOUNT_ROOT


# ---------------------------
# Helpers
# ---------------------------

_INVALID_FS_CHARS = r'<>:"/\\|?*\x00-\x1F'


def _clean_segment(value: str) -> str:
    """
    Limpia un segmento de ruta para uso seguro en filesystem.
    """
    v = (value or "").strip()
    v = re.sub(r"\s+", " ", v)
    v = re.sub(f"[{_INVALID_FS_CHARS}]", "", v)
    v = v.strip().strip(".")
    return v or "SIN_NOMBRE"


def _carpeta_trabajador(ap_paterno: str, ap_materno: str, nombres: str) -> str:
    """
    Formato legacy requerido:
    "<Ap_Paterno> <Ap_Materno> <Nombres>"
    """
    return f"{_clean_segment(ap_paterno)} {_clean_segment(ap_materno)} {_clean_segment(nombres)}"


# ---------------------------
# Paths
# ---------------------------

@dataclass(frozen=True)
class NextcloudPaths:
    mount_root: Path

    def base(self) -> Path:
        return self.mount_root

    def dir_trabajador(
        self,
        *,
        centro_costo: str,
        nombres: str,
        ap_paterno: str,
        ap_materno: str,
        tipo_doc: str,
    ) -> Path:
        """
        RUTA FINAL:

        /<CENTRO_DE_COSTO>/Laboral/Trabajadores/
            <Ap_Paterno> <Ap_Materno> <Nombres>/<TIPO_DOC>/
        """
        cc = _clean_segment(centro_costo)
        carpeta_persona = _carpeta_trabajador(ap_paterno, ap_materno, nombres)
        carpeta_tipo = _clean_segment(tipo_doc).upper()

        return (
            self.mount_root
            / cc
            / "Laboral"
            / "Trabajadores"
            / carpeta_persona
            / carpeta_tipo
        )


def get_nc_paths() -> NextcloudPaths:
    return NextcloudPaths(
        mount_root=Path(NEXTCLOUD_MOUNT_ROOT)
    )
