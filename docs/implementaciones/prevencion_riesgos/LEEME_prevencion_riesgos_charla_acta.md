# Prevención de Riesgos - Acta imprimible de Charla de Seguridad

Este paquete agrega una vista imprimible para las charlas de seguridad.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/charlas/<id>/imprimir`

- Nuevo template:
  - `web/app/templates/prevencion_riesgos/charla_imprimir.html`

- Mejora en detalle:
  - Botón `Imprimir acta`

## Características del acta

- Datos generales de la charla.
- Obra, fecha, tipo, duración y relator.
- Tema/contenido tratado.
- Observaciones.
- Listado de asistentes.
- Columna de firma con espacio amplio.
- Firmas finales de relator/supervisor y responsable empresa.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_charla_acta_grupo_cs.zip -d /srv/rrhh_app
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

Entrar al detalle de una charla y presionar `Imprimir acta`.
