# Implementación 2026-06-03 · Roles y permisos V9

## Objetivo

Fortalecer el control de acceso basado en roles/permisos del Sistema Grupo CS, pasando desde una etapa de visibilidad de menús a una primera barrera real por módulo.

## Versión

`2026.06.03-v9`

## Cambios principales

- Se agregó una barrera central `before_request` para validar permisos por módulo/blueprint.
- Se incorporó una matriz `BLUEPRINT_PERMISSION_RULES` en `web/app/services/access_control.py`.
- Se diferencian permisos de lectura y operación según:
  - método HTTP (`POST`, `PUT`, `PATCH`, `DELETE` exigen permiso operativo);
  - endpoints GET con nombres funcionales como `nuevo`, `editar`, `generar`, `emitir`, `importar`, `aprobar`, etc.
- Se agregaron decoradores `permission_required()` y `any_permission_required()` para preparar la V10 de protección de acciones críticas.
- Se actualizó la pantalla `Admin → Roles y permisos` para mostrar los módulos protegidos por la barrera V9.

## Alcance conservador

Esta V9 no modifica la base de datos y no requiere migraciones Alembic. Usa la estructura existente de roles múltiples y permisos calculados en código.

## Validación recomendada

1. Entrar como ADMIN y verificar `Admin → Roles y permisos`.
2. Entrar con un usuario no ADMIN y confirmar que el navbar oculta secciones no autorizadas.
3. Intentar acceder por URL directa a un módulo sin permiso y confirmar pantalla 403 corporativa.
4. Probar usuarios con combinaciones:
   - `FINANZAS`
   - `ADMINISTRATIVO`
   - `JEFATURA`
   - `PREVENCION`
   - `SOLO_LECTURA`
   - `RENDIDOR`

## Próxima etapa sugerida

V10: proteger acciones críticas específicas con decoradores por endpoint, por ejemplo:

- crear/editar trabajador;
- generar contrato;
- emitir anexo;
- aprobar solicitud de fondos;
- generar nómina bancaria;
- eliminar/anular documentos.
