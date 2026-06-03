#!/usr/bin/env bash
set -Eeuo pipefail

# Genera un ZIP limpio del Sistema Grupo CS para revisión técnica o envío de parches.
# Uso básico:
#   ./scripts/generar_zip_limpio.sh
#
# Opciones:
#   ./scripts/generar_zip_limpio.sh --output-dir /srv/exports
#   ./scripts/generar_zip_limpio.sh --name rrhh_app_limpio.zip
#   ./scripts/generar_zip_limpio.sh --include-env   # NO recomendado; solo para respaldo interno controlado.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="${PROJECT_ROOT}/_exports"
ZIP_NAME="${PROJECT_NAME}_limpio_${TIMESTAMP}.zip"
INCLUDE_ENV="0"

usage() {
  cat <<USAGE
Uso: $0 [opciones]

Opciones:
  --output-dir RUTA   Carpeta donde se guardará el ZIP. Por defecto: ${OUTPUT_DIR}
  --name NOMBRE.zip   Nombre del archivo ZIP. Por defecto: ${ZIP_NAME}
  --include-env       Incluye .env y .env.*. No recomendado para compartir.
  -h, --help          Muestra esta ayuda.

Ejemplo:
  $0 --output-dir /srv/exports --name rrhh_app_para_revision.zip
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: falta la ruta para --output-dir" >&2; exit 1; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --name)
      [[ $# -ge 2 ]] || { echo "ERROR: falta el nombre para --name" >&2; exit 1; }
      ZIP_NAME="$2"
      shift 2
      ;;
    --include-env)
      INCLUDE_ENV="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: opción no reconocida: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v zip >/dev/null 2>&1; then
  echo "ERROR: el comando 'zip' no está instalado." >&2
  echo "Instálalo con: sudo apt update && sudo apt install -y zip" >&2
  exit 1
fi

case "${ZIP_NAME}" in
  *.zip) ;;
  *) ZIP_NAME="${ZIP_NAME}.zip" ;;
esac

mkdir -p "${OUTPUT_DIR}"
OUTPUT_PATH="${OUTPUT_DIR}/${ZIP_NAME}"
rm -f "${OUTPUT_PATH}"

EXCLUDES=(
  "${PROJECT_NAME}/.git/*"
  "${PROJECT_NAME}/.git"
  "${PROJECT_NAME}/.codex"
  "${PROJECT_NAME}/backups/*"
  "${PROJECT_NAME}/backups"
  "${PROJECT_NAME}/data/db/*"
  "${PROJECT_NAME}/data/db"
  "${PROJECT_NAME}/_exports/*"
  "${PROJECT_NAME}/_exports"
  "${PROJECT_NAME}/exports/*"
  "${PROJECT_NAME}/exports"
  "${PROJECT_NAME}/tmp/*"
  "${PROJECT_NAME}/tmp"
  "${PROJECT_NAME}/temp/*"
  "${PROJECT_NAME}/temp"
  "${PROJECT_NAME}/logs/*"
  "${PROJECT_NAME}/logs"
  "${PROJECT_NAME}/web/app/document_templates/output/*"
  "${PROJECT_NAME}/web/app/document_templates/output"
  "${PROJECT_NAME}/**/__pycache__/*"
  "${PROJECT_NAME}/**/__pycache__"
  "${PROJECT_NAME}/**/.pytest_cache/*"
  "${PROJECT_NAME}/**/.pytest_cache"
  "${PROJECT_NAME}/**/.mypy_cache/*"
  "${PROJECT_NAME}/**/.mypy_cache"
  "${PROJECT_NAME}/**/.ruff_cache/*"
  "${PROJECT_NAME}/**/.ruff_cache"
  "${PROJECT_NAME}/**/.DS_Store"
  "${PROJECT_NAME}/**/Thumbs.db"
  "${PROJECT_NAME}/**/*.pyc"
  "${PROJECT_NAME}/**/*.pyo"
  "${PROJECT_NAME}/**/*.log"
  "${PROJECT_NAME}/**/*.bak"
  "${PROJECT_NAME}/**/*.bak_*"
  "${PROJECT_NAME}/**/*~"
  "${PROJECT_NAME}/**/*.swp"
  "${PROJECT_NAME}/**/*.swo"
  "${PROJECT_NAME}/**/.venv/*"
  "${PROJECT_NAME}/**/.venv"
  "${PROJECT_NAME}/**/venv/*"
  "${PROJECT_NAME}/**/venv"
  "${PROJECT_NAME}/**/node_modules/*"
  "${PROJECT_NAME}/**/node_modules"
)

if [[ "${INCLUDE_ENV}" != "1" ]]; then
  EXCLUDES+=(
    "${PROJECT_NAME}/.env"
    "${PROJECT_NAME}/.env.*"
  )
fi

cd "${PROJECT_ROOT}/.."

zip -r -q "${OUTPUT_PATH}" "${PROJECT_NAME}" -x "${EXCLUDES[@]}"

BYTES="$(stat -c%s "${OUTPUT_PATH}" 2>/dev/null || wc -c < "${OUTPUT_PATH}")"
HUMAN_SIZE="$(du -h "${OUTPUT_PATH}" | awk '{print $1}')"

cat <<OK
✅ ZIP limpio generado correctamente
Archivo : ${OUTPUT_PATH}
Tamaño  : ${HUMAN_SIZE} (${BYTES} bytes)

Excluido por seguridad/orden:
- .git/
- .env y .env.* ${INCLUDE_ENV:+}
- backups/
- data/db/
- __pycache__, *.pyc, logs, temporales y salidas generadas
OK

if [[ "${INCLUDE_ENV}" == "1" ]]; then
  cat <<WARN

⚠️  Atención: generaste el ZIP con --include-env.
   Úsalo solo para respaldo interno controlado. No lo compartas como archivo de revisión.
WARN
fi
