# Implementación 2026-06-03 · Salud del sistema y versión visible

## Objetivo

Incorporar una mejora administrativa de bajo riesgo para apoyar operación y soporte del Sistema Grupo CS:

- Versión visible del sistema en el footer.
- Archivo `VERSION` en la raíz del proyecto.
- Panel administrativo `/admin/salud-sistema`.
- Servicio técnico `system_health.py` para revisar estado básico de componentes críticos.

## Archivos modificados

- `VERSION`
- `web/app/__init__.py`
- `web/app/blueprints/admin/routes.py`
- `web/app/services/system_health.py`
- `web/app/templates/admin/salud_sistema.html`
- `web/app/templates/base.html`
- `web/app/static/styles.css`

## Panel disponible

Ruta:

```text
/admin/salud-sistema
```

Acceso:

```text
Solo usuarios con rol ADMIN
```

Controles incluidos:

- Versión del sistema.
- Base de datos mediante `SELECT 1`.
- Variables críticas de entorno.
- Espacio en disco del proyecto.
- Montaje Nextcloud, cuando existe configuración por variables de entorno.

## Nota operativa

El panel no reemplaza la revisión de logs con Docker, pero permite detectar rápidamente problemas básicos antes de iniciar una investigación más profunda.
