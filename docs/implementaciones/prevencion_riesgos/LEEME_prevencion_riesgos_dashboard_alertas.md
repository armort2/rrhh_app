# Prevención de Riesgos - Dashboard con Alertas

Este paquete mejora el dashboard preventivo agregando alertas operativas.

## Cambios incluidos

- KPIs de reposiciones EPP vencidas.
- KPIs de reposiciones EPP por vencer.
- Listado de documentos vencidos.
- Listado de documentos por vencer.
- Listado de reposiciones EPP vencidas.
- Listado de reposiciones EPP por vencer.
- Ventana de alerta de 30 días.

## Archivos modificados

- `web/app/blueprints/prevencion_riesgos/queries.py`
- `web/app/templates/prevencion_riesgos/dashboard.html`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_dashboard_alertas_grupo_cs.zip -d /srv/rrhh_app
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/queries.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose restart web
```

## Prueba

Abrir:

```text
https://sistema.grupo-cs.cl/prevencion-riesgos/
```
