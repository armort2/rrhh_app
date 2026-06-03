# Prevención de Riesgos - Acta imprimible de Entrega de EPP

Este paquete agrega una vista imprimible para las entregas de EPP.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/epp/<id>/imprimir`

- Nuevo template:
  - `web/app/templates/prevencion_riesgos/epp_imprimir.html`

- Mejora en detalle:
  - Botón `Imprimir acta`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_epp_acta_grupo_cs.zip -d /srv/rrhh_app
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep prevencion
```

## Uso

Entrar al detalle de una entrega de EPP y presionar `Imprimir acta`.
