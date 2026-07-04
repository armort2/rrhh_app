# Fase 2 · Expediente Laboral 360

## Objetivo

Consolidar la ficha del trabajador y el detalle del contrato como pantallas de control operativo, no solo de consulta. La mejora agrega semáforos, alertas, recomendaciones y métricas para reducir pasos manuales al generar documentación laboral.

## Cambios incluidos

- Nuevo servicio `web/app/services/expediente_laboral.py`.
- Semáforo de salud del expediente en ficha del trabajador.
- Acciones sugeridas en ficha del trabajador.
- Panel `Contrato 360` en detalle de contrato.
- Alertas contractuales por vencimiento, sueldo bajo mínimo parametrizado, jornada sobre 42 horas, falta de datos y ausencia de documentos.
- Acciones recomendadas por contrato: completar, generar contrato, extensión, paso a indefinido, cambio de sueldo y volver al expediente.
- Estilos CSS corporativos para paneles 360.

## Consideraciones técnicas

- No agrega migraciones.
- No modifica datos en base.
- Usa `parametros_laborales.renta_minima_dependiente` si existe un parámetro vigente; si no, solo muestra “No cargado”.
- Las recomendaciones son de apoyo operativo; la decisión laboral sigue siendo del usuario responsable.

## Validación sugerida

```bash
cd /srv/rrhh_app
python -m compileall -q web/app
# o dentro del contenedor:
docker compose exec web python -m compileall -q /app
```

Revisar:

- `/trabajadores/<id>`
- `/contratos/<id>`

