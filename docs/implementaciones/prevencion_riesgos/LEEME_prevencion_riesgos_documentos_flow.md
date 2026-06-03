# Prevención de Riesgos - Flujo Documentos Preventivos

Este paquete agrega el flujo inicial de documentos preventivos por trabajador.

## Cambios incluidos

- Listado de documentos preventivos.
- Nuevo documento preventivo.
- Detalle de documento preventivo.
- Estados automáticos según vencimiento:
  - Vigente
  - Por vencer
  - Vencido
- Filtros por trabajador, obra, tipo y estado.
- Acceso en menú principal.
- Acceso rápido desde dashboard preventivo.

## Rutas nuevas

- `/prevencion-riesgos/documentos`
- `/prevencion-riesgos/documentos/nuevo`
- `/prevencion-riesgos/documentos/<id>`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_documentos_flow_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_documentos_menu.py
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

## Nota

Este flujo registra metadatos y referencias de archivo. La carga real de archivos o integración directa con Nextcloud puede implementarse en una etapa posterior.
