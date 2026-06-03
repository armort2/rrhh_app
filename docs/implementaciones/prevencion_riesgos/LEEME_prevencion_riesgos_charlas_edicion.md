# Prevención de Riesgos - Edición de Charlas de Seguridad

Este paquete agrega edición de charlas de seguridad y asistentes.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/charlas/<id>/editar`

- Script de parche:
  - `scripts/patch_prevencion_charlas_edicion.py`

- Templates actualizados:
  - `charla_form.html`
  - `charla_detalle.html`
  - `charlas_listado.html`

## Funcionalidad

Permite editar:

- Obra
- Título
- Tipo
- Fecha
- Relator
- Duración
- Tema / contenido
- Observación
- Asistentes

## Nota sobre asistentes

Al guardar una edición, el sistema reemplaza el listado de asistentes por los seleccionados en el formulario.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_charlas_edicion_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_charlas_edicion.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep charlas
```

## Uso

Entrar al listado o detalle de charlas de seguridad y presionar `Editar`.
