# web/app/config.py

import os
import unicodedata
from datetime import date
from pathlib import Path

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    """Configuración base (común a todos los entornos)."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_key")

    # Si no viene DATABASE_URL desde el entorno, usamos un SQLite local
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "rrhh_app_dev.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevConfig(BaseConfig):
    """Configuración para desarrollo."""
    DEBUG = True


class ProdConfig(BaseConfig):
    """Configuración para producción."""
    DEBUG = False


# ==========================
# Configuración Nextcloud / Documentación laboral
# ==========================

# Ruta base LÓGICA dentro de Nextcloud (no incluye URL del servidor, solo la “carpeta”)
NEXTCLOUD_BASE_PATH = (
    "DOCUMENTACION LABORAL/EMPLEADORES/{empleador}/TRABAJADORES/{carpeta_trabajador}"
)


def normalizar_nombre_trabajador(rut: str, nombres: str, ap_paterno: str, ap_materno: str) -> str:
    """
    Genera nombre de carpeta estándar:
    12345710-2_PAILLALEVE_GUINEO_HECTOR_DAVID

    - El RUT va SIN PUNTOS, con guión y DV.
    - Nombres y apellidos en MAYÚSCULAS, sin tildes.
    - Espacios -> guiones bajos.
    """

    def _clean(texto: str) -> str:
        if not texto:
            return ""
        txt = texto.strip().upper()
        txt_norm = unicodedata.normalize("NFD", txt)
        txt_sin_tildes = "".join(
            ch for ch in txt_norm
            if unicodedata.category(ch) != "Mn"
        )
        return txt_sin_tildes.replace(" ", "_")

    # RUT: sin puntos, pero respetando el guión
    rut_limpio = (rut or "").strip().replace(".", "").upper()

    return "_".join([
        rut_limpio,
        _clean(ap_paterno),
        _clean(ap_materno),
        _clean(nombres),
    ])


def _normalizar_texto_simple(texto: str) -> str:
    """
    Normaliza texto para usar en nombres de archivo:
    - MAYÚSCULAS
    - sin tildes
    - espacios -> _
    """
    if not texto:
        return ""
    txt = texto.strip().upper()
    txt_norm = unicodedata.normalize("NFD", txt)
    txt_sin_tildes = "".join(
        ch for ch in txt_norm
        if unicodedata.category(ch) != "Mn"
    )
    return txt_sin_tildes.replace(" ", "_")


def generar_nombre_documento(
    tipo: str,
    ap_paterno: str,
    fecha_ref: date | None,
    extension: str = "pdf",
) -> str:
    """
    Genera un nombre de archivo estándar, por ejemplo:

        CONTRATO_INDEFINIDO_PAILLALEVE_2025-03-01.pdf
    """
    tipo_norm = _normalizar_texto_simple(tipo)
    ap_norm = _normalizar_texto_simple(ap_paterno)
    ext = (extension or "pdf").lower().lstrip(".")

    fecha_str = fecha_ref.strftime("%Y-%m-%d") if fecha_ref else "SIN_FECHA"

    return f"{tipo_norm}_{ap_norm}_{fecha_str}.{ext}"


# ==========================
# Tipos de documento = carpetas en Nextcloud
# ==========================

DOCUMENTO_TIPOS = [
    ("CONTRATOS", "Contratos"),
    ("ANEXOS", "Anexos"),
    ("FINIQUITOS", "Finiquitos"),
    ("PERMISOS", "Permisos / Licencias"),
    ("ACUERDOS", "Acuerdos"),
    ("CARTAS_AVISO", "Cartas de aviso"),
    ("AMONESTACIONES", "Amonestaciones"),
]


def get_nextcloud_base_path() -> Path:
    """
    Retorna la carpeta base en el servidor donde están los documentos laborales
    sincronizados con Nextcloud (por ejemplo: /mnt/nextcloud/DOCUMENTACION LABORAL).

    Si no se define la variable de entorno NEXTCLOUD_ROOT, se usa ese valor por defecto.
    """
    root = os.environ.get("NEXTCLOUD_ROOT", "/mnt/nextcloud/DOCUMENTACION LABORAL")
    return Path(root)
