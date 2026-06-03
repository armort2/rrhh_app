# Generación de ZIP limpio del Sistema Grupo CS

Este documento describe el uso del script `scripts/generar_zip_limpio.sh`, incorporado para generar copias limpias del proyecto antes de enviarlo a revisión técnica o usarlo como base para nuevos parches.

## Uso recomendado

Desde la raíz del proyecto:

```bash
cd /srv/rrhh_app
./scripts/generar_zip_limpio.sh
```

Por defecto, el archivo se guarda en:

```text
/srv/rrhh_app/_exports/
```

Con un nombre similar a:

```text
rrhh_app_limpio_20260603_001530.zip
```

## Generar el ZIP en otra carpeta

```bash
cd /srv/rrhh_app
./scripts/generar_zip_limpio.sh --output-dir /srv/exports
```

## Definir un nombre específico

```bash
cd /srv/rrhh_app
./scripts/generar_zip_limpio.sh --output-dir /srv/exports --name rrhh_app_para_revision.zip
```

## Exclusiones principales

El ZIP limpio excluye:

- `.git/`
- `.env` y `.env.*`
- `backups/`
- `data/db/`
- `_exports/`
- `__pycache__/`
- `*.pyc`
- `*.log`
- archivos temporales y respaldos `*.bak`, `*.bak_*`
- salidas generadas en `web/app/document_templates/output/`

## Nota de seguridad

El script tiene una opción `--include-env`, pero no se recomienda usarla para archivos que serán compartidos. El `.env` puede contener credenciales, claves secretas o parámetros sensibles de producción.
