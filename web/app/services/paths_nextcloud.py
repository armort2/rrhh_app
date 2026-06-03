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

    OJO:
    - Ya NO devolvemos "SIN_NOMBRE" aquí, porque hay casos válidos donde el dato
      puede venir vacío (ej: ap_materno en algunos trabajadores).
    - El fallback "SIN_NOMBRE" se aplica SOLO al final, cuando el nombre completo
      queda vacío.
    """
    v = (value or "").strip()
    v = re.sub(r"\s+", " ", v)
    v = re.sub(f"[{_INVALID_FS_CHARS}]", "", v)
    v = v.strip().strip(".")
    return v


def _carpeta_trabajador(ap_paterno: str, ap_materno: str, nombres: str) -> str:
    """
    Formato legacy requerido:
      "<Ap_Paterno> <Ap_Materno> <Nombres>"

    Pero:
    - Si ap_materno viene vacío, NO se rellena con SIN_NOMBRE.
    - Se eliminan partes vacías y se mantiene un nombre de carpeta limpio.
    - Fallback final: "SIN_NOMBRE" solo si todo quedara vacío (caso patológico).
    """
    parts = [
        _clean_segment(ap_paterno),
        _clean_segment(ap_materno),
        _clean_segment(nombres),
    ]
    parts = [p for p in parts if p]  # 👈 elimina vacíos

    return " ".join(parts) if parts else "SIN_NOMBRE"


def _clean_required_segment(value: str) -> str:
    """
    Variante para segmentos obligatorios de la ruta (ej: centro de costo, tipo_doc).
    Aquí sí aplicamos fallback porque la ruta se rompería si queda vacío.
    """
    v = _clean_segment(value)
    return v or "SIN_NOMBRE"


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
        cc = _clean_required_segment(centro_costo)
        carpeta_persona = _carpeta_trabajador(ap_paterno, ap_materno, nombres)
        carpeta_tipo = _clean_required_segment(tipo_doc).upper()

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
