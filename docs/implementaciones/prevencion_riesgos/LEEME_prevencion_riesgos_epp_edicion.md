# Prevención de Riesgos - Edición de Entregas de EPP

Este paquete agrega edición de entregas de EPP y sus items.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/epp/<id>/editar`

- Script de parche:
  - `scripts/patch_prevencion_epp_edicion.py`

- Templates actualizados:
  - `epp_form.html`
  - `epp_detalle.html`
  - `epp_listado.html`

## Funcionalidad

Permite editar:

- Trabajador
- Obra
- Fecha de entrega
- Observación general
- Items entregados
- Cantidades
- Tallas
- Marca/modelo
- Fecha de reposición sugerida
- Observación por item

## Nota sobre items

Al guardar una edición, el sistema reemplaza el detalle de items por los indicados en el formulario.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_epp_edicion_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_epp_edicion.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep epp
```

## Uso

Entrar al listado o detalle de entregas de EPP y presionar `Editar`.
