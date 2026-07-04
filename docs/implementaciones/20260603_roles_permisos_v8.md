# Implementación V8 · Roles y permisos institucionales

## Objetivo

Ordenar el control de acceso del Sistema Grupo CS usando roles funcionales combinables, manteniendo compatibilidad con los roles históricos mientras se endurecen permisos por etapas.

## Roles incorporados

- ADMIN
- FINANZAS
- ADMINISTRATIVO
- JEFATURA
- PREVENCION
- SOLO_LECTURA
- RENDIDOR
- OPERADOR, histórico
- REVISOR, histórico

## Archivos principales

- `web/app/services/access_control.py`
- `web/app/templates/admin/roles_matriz.html`
- `web/app/templates/admin/user_form.html`
- `web/app/templates/base.html`
- `web/app/cli.py`
- `web/app/__init__.py`
- `web/app/models_legacy.py`

## Puesta en marcha

Luego de aplicar el parche, ejecutar:

```bash
flask seed-roles
```

En Docker:

```bash
docker compose exec web flask seed-roles
```

## Alcance conservador

Esta versión introduce la matriz institucional, los helpers `current_user_can()` y `current_user_has_any_permission()`, mejora el formulario de usuarios y ajusta la visibilidad de menús principales.

Las rutas profundas todavía conservan decoradores históricos en varios módulos. La V9 debería endurecer rutas por módulo/acción para aplicar permisos de manera estricta.
