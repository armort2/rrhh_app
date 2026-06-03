# Prevención de Riesgos - Flujo Charlas de Seguridad

Este paquete agrega el flujo inicial de charlas de seguridad.

## Cambios incluidos

- Listado de charlas.
- Nueva charla.
- Detalle de charla.
- Registro de asistentes.
- Acceso en menú principal.
- Acceso rápido desde dashboard preventivo.

## Rutas nuevas

- `/prevencion-riesgos/charlas`
- `/prevencion-riesgos/charlas/nueva`
- `/prevencion-riesgos/charlas/<id>`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_charlas_flow_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_charlas_menu.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/blueprints/prevencion_riesgos/routes.py \
  /app/app/blueprints/prevencion_riesgos/constants.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep prevencion
```
