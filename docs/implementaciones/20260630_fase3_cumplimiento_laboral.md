# Fase 3 · Cumplimiento Laboral

## Objetivo
Incorporar un panel ejecutivo de cumplimiento laboral para monitorear riesgos operativos de RRHH y prevención sin modificar la estructura de base de datos.

## Alcance
- Nuevo módulo `/cumplimiento-laboral/`.
- Panel de alertas laborales y preventivas.
- Control de:
  - contratos vigentes con fecha vencida;
  - contratos próximos a vencer;
  - jornadas superiores a 42 horas;
  - sueldos base bajo el mínimo parametrizado;
  - parámetros laborales del período actual;
  - documentos preventivos vencidos o por vencer;
  - reposiciones de EPP vencidas.
- Priorización por obra según carga de alertas.
- Checklist inicial de Ley Karin en `/cumplimiento-laboral/ley-karin`.

## Archivos agregados
- `web/app/blueprints/cumplimiento_laboral/__init__.py`
- `web/app/blueprints/cumplimiento_laboral/routes.py`
- `web/app/services/cumplimiento_laboral.py`
- `web/app/templates/cumplimiento_laboral/index.html`
- `web/app/templates/cumplimiento_laboral/ley_karin.html`

## Archivos modificados
- `web/app/__init__.py`
- `web/app/services/access_control.py`
- `web/app/templates/base.html`
- `web/app/static/styles.css`

## Migraciones
No requiere migraciones.

## Validación sugerida
```bash
flask routes | grep cumplimiento
python -m compileall -q /app
```

Luego abrir:
- `/cumplimiento-laboral/`
- `/cumplimiento-laboral/ley-karin`
