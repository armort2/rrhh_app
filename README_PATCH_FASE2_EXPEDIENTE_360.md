# Parche Fase 2 · Expediente Laboral 360

## Archivos incluidos

- `web/app/services/expediente_laboral.py`
- `web/app/blueprints/trabajadores/routes.py`
- `web/app/templates/trabajadores/trabajador_detalle.html`
- `web/app/blueprints/contratos/routes.py`
- `web/app/templates/contratos/contrato_detalle.html`
- `web/app/static/styles.css`
- `docs/implementaciones/20260630_fase2_expediente_360.md`

## Qué agrega

- Semáforo de salud del expediente en ficha del trabajador.
- Recomendaciones operativas en ficha del trabajador.
- Panel Contrato 360 en detalle de contrato.
- Alertas por vencimiento, jornada sobre 42 horas, falta de datos, ausencia de documentos y sueldo bajo mínimo parametrizado.
- Acciones sugeridas para completar contrato, generar documentos, extender contrato, pasar a indefinido o cambiar sueldo.

## Base de datos

No incluye migraciones. No modifica estructura ni datos.

## Aplicación recomendada

```bash
cd /srv/rrhh_app
cp -a . ../rrhh_app_backup_antes_fase2_expediente_360_$(date +%Y%m%d_%H%M%S)
unzip -o rrhh_app_patch_fase2_expediente_360.zip
docker compose up -d --build
docker compose exec web python -m compileall -q /app
docker compose logs --tail=120 web
```

## Validación funcional

- Abrir una ficha de trabajador: `/trabajadores/<id>`.
- Confirmar bloque “Salud del expediente”.
- Confirmar bloque “Acciones sugeridas”.
- Abrir un contrato: `/contratos/<id>`.
- Confirmar bloque “Contrato 360”.
- Revisar que las acciones sugeridas apunten a los módulos correctos.

