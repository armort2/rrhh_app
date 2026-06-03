# web/app/config.py

import os
import unicodedata
from datetime import date
from pathlib import Path

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    """Configuración base (común a todos los entornos)."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_key")

    # Base de datos principal del sistema.
    # En producción y desarrollo Docker debe venir siempre desde DATABASE_URL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(
            "DATABASE_URL no está configurada. "
            "Revisa el archivo .env o las variables de entorno del contenedor."
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Rutas de plantillas para desvinculaciones
    DESVINCULACION_TEMPLATES_DIR = "document_templates/desvinculacion"
    FINIQUITO_TEMPLATE_NAME = "finiquito.docx"
    CARTA_AVISO_DEFAULT_TEMPLATE_NAME = "carta_aviso.docx"  # opcional, fallback corporativo

    # Librería de descripciones de cargo (bookmarks CARGO_{id}__DESCRIPCION)
    CARGOS_LIBRARY_TEMPLATE = "document_templates/contratos/cargos.docx"


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

NEXTCLOUD_WEBDAV_URL = os.environ.get("NEXTCLOUD_WEBDAV_URL", "").rstrip("/")
NEXTCLOUD_USERNAME = os.environ.get("NEXTCLOUD_USERNAME", "")
NEXTCLOUD_PASSWORD = os.environ.get("NEXTCLOUD_PASSWORD", "")


def normalizar_nombre_trabajador(rut: str, nombres: str, ap_paterno: str, ap_materno: str) -> str:
    """

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

# ==========================
# Nextcloud montado (rclone mount)
# ==========================

# Root del mount (en el server)
NEXTCLOUD_MOUNT_ROOT = os.environ.get("NEXTCLOUD_MOUNT_ROOT", "/mnt/GrupoCS-Nextcloud")

# Carpeta base dentro de Nextcloud (elige una sola convención)
NEXTCLOUD_DOC_ROOT = os.environ.get("NEXTCLOUD_DOC_ROOT", "DOCUMENTACION LABORAL")

# Estructura fija (convención corporativa)
NEXTCLOUD_PATH_TEMPLATE = (
    "{doc_root}/EMPLEADORES/{empleador}/TRABAJADORES/{carpeta_trabajador}/{tipo_doc}"
)

