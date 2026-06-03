# Prevención de Riesgos - Acta imprimible de Entrega de Documentación Preventiva

Este paquete agrega una vista imprimible para documentos preventivos.

## Cambios incluidos

- Nueva ruta:
  - `/prevencion-riesgos/documentos/<id>/imprimir`

- Nuevo template:
  - `web/app/templates/prevencion_riesgos/documento_imprimir.html`

- Mejora en detalle:
  - Botón `Imprimir acta`

## Características del acta

- Datos del trabajador.
- Obra asociada.
- Tipo de documento.
- Fecha de emisión y vencimiento.
- Estado del documento.
- Nombre de archivo y referencia/ruta.
- Observaciones.
- Declaración de recepción / toma de conocimiento.
- Firmas de trabajador y empresa.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_documento_acta_grupo_cs.zip -d /srv/rrhh_app
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

Entrar al detalle de un documento preventivo y presionar `Imprimir acta`.
