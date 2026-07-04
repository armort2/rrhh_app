# Fase 6 · Plan mensual RRHH

## Objetivo
Convertir la Bandeja de Gestión RRHH en una herramienta de seguimiento periódico, agrupando tareas por horizonte de atención:

- vencidas / hoy;
- próximos 7 días;
- semana siguiente;
- resto del mes;
- gestiones sin fecha directa;
- posterior a 30 días, si corresponde.

## Rutas nuevas

- `/gestion-rrhh/plan-mensual`
- `/gestion-rrhh/plan-mensual/exportar.csv`

## Cambios funcionales

- Nuevo tablero de **Plan mensual RRHH**.
- KPIs del plan: tareas visibles, vencidas/hoy, próximos 7 días y prioridad alta.
- Agrupación de tareas por horizonte operativo.
- Checklist mensual de RRHH:
  - parámetros laborales;
  - comité de contratos por vencer;
  - control de jornada 42 horas;
  - semáforo preventivo;
  - exportación de evidencia.
- Acciones masivas sugeridas según categorías detectadas en bandeja.
- Exportación CSV del plan mensual.
- Acceso desde el menú Dashboard y desde la Bandeja de Gestión RRHH.

## Archivos modificados

- `web/app/blueprints/gestion_rrhh/routes.py`
- `web/app/services/gestion_rrhh.py`
- `web/app/templates/gestion_rrhh/index.html`
- `web/app/templates/gestion_rrhh/plan_mensual.html`
- `web/app/templates/base.html`
- `web/app/static/styles.css`

## Base de datos

No requiere migraciones. Esta fase trabaja sobre señales existentes de Cumplimiento Laboral y Bandeja de Gestión RRHH.

## Validación sugerida

```bash
cd /srv/rrhh_app
unzip -o rrhh_app_patch_fase6_plan_mensual_rrhh.zip
docker compose up -d --build
docker compose exec web python -m compileall -q /app
docker compose exec web flask routes | grep gestion_rrhh
```

Luego abrir:

- `/gestion-rrhh/`
- `/gestion-rrhh/plan-mensual`
- `/gestion-rrhh/plan-mensual/exportar.csv`
