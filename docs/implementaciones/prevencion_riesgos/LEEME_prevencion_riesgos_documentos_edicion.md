# Prevención de Riesgos - Edición de Documentos Preventivos

Este paquete agrega edición de documentos preventivos.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/documentos/<id>/editar`

- Actualización de:
  - `routes.py`
  - `documento_form.html`
  - `documento_detalle.html`
  - `documentos_listado.html`

## Funcionalidad

Permite editar:

- Trabajador
- Obra
- Tipo de documento
- Fecha de emisión
- Fecha de vencimiento
- Estado
- Nombre de archivo
- Ruta / enlace de archivo
- Observación

## Regla de estado

El estado se recalcula automáticamente según vencimiento, salvo si se selecciona:

- `PENDIENTE`
- `ANULADO`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_documentos_edicion_grupo_cs.zip -d /srv/rrhh_app
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep documentos
```

## Uso

Entrar al listado o detalle de documentos preventivos y presionar `Editar`.
