# Implementación v2026.06.03-v7 · Bitácora / Auditoría

## Objetivo

Agregar trazabilidad básica del uso del Sistema Grupo CS para revisar qué usuarios entran a qué secciones, rutas consultadas, métodos ejecutados, códigos de respuesta e información operacional básica.

## Cambios principales

- Nuevo modelo `AuditLog`.
- Nueva migración Alembic `a1b2c3d4e5f7_add_audit_logs.py`.
- Nuevo servicio `web/app/services/audit.py`.
- Registro automático de requests autenticados.
- Registro manual de eventos `login` y `logout`.
- Nueva vista administrativa `Admin → Bitácora / Auditoría`.
- Filtros por usuario, sección, tipo de evento, método, fechas y texto libre.
- Métricas rápidas de usuarios activos y secciones más usadas en los últimos 7 días.

## Ruta

```text
/admin/auditoria
```

## Consideraciones

El servicio es defensivo: si la tabla `audit_logs` todavía no existe, no rompe la navegación. De todos modos, después de aplicar el parche se debe ejecutar la migración.
