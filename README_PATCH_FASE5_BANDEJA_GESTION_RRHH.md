# Fase 5 · Bandeja de Gestión RRHH

## Objetivo
Convertir las alertas del Centro de Cumplimiento Laboral en una bandeja operativa priorizada, con tareas accionables para RRHH, prevención y administración.

## Qué incluye

### Nuevo módulo
- URL: `/gestion-rrhh/`
- Blueprint: `gestion_rrhh`
- Menú: Dashboard → Bandeja de gestión RRHH

### Funcionalidades
- Tareas priorizadas por criticidad:
  - Alta
  - Media
  - Baja
- Categorías:
  - Contratos
  - Jornada
  - Remuneraciones
  - Prevención
  - Parámetros
  - Datos maestros
- Filtros por prioridad, categoría y texto libre.
- Atajos directos al contrato, prevención, anexos masivos y cumplimiento laboral.
- Exportación CSV de la bandeja filtrada.

## Archivos agregados
- `web/app/blueprints/gestion_rrhh/__init__.py`
- `web/app/blueprints/gestion_rrhh/routes.py`
- `web/app/services/gestion_rrhh.py`
- `web/app/templates/gestion_rrhh/index.html`

## Archivos modificados
- `web/app/__init__.py`
- `web/app/services/access_control.py`
- `web/app/templates/base.html`
- `web/app/static/styles.css`

## Base de datos
No requiere migraciones. Esta fase trabaja sobre datos existentes y sobre el servicio de cumplimiento laboral ya implementado.

## Validación sugerida
```bash
docker compose exec web flask routes | grep gestion_rrhh
```

Abrir:

```text
/gestion-rrhh/
```

Probar:
- filtro por prioridad alta;
- filtro por jornada;
- botón exportar CSV;
- enlaces de tareas hacia contrato/previsión/anexos/cumplimiento.
