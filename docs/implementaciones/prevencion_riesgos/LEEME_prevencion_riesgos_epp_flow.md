# Prevención de Riesgos - Flujo Entrega de EPP

Este paquete agrega el primer flujo operativo del módulo:

- Listado de entregas de EPP.
- Nueva entrega.
- Detalle de entrega.
- Registro de múltiples items por entrega.
- Acceso en menú principal.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_epp_flow_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_epp_menu.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep prevencion
```

## Rutas nuevas

- `/prevencion-riesgos/epp`
- `/prevencion-riesgos/epp/nueva`
- `/prevencion-riesgos/epp/<id>`
