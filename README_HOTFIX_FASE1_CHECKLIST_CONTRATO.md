# Hotfix Fase 1 · Checklist documental contrato

Este hotfix corrige el error:

```text
jinja2.exceptions.UndefinedError: 'documento_checklist' is undefined
```

## Cambios incluidos

- `web/app/templates/contratos/contrato_detalle.html`
  - Agrega valores defensivos por defecto para `documento_checklist` y `documentos_registrados`.
  - La pantalla del contrato queda operativa aunque la ruta no envíe temporalmente el contexto documental.

- `web/app/blueprints/contratos/routes.py`
  - Refuerza `contrato_detalle` para construir el checklist documental y cargar últimos documentos registrados.
  - Agrega fallback con logging si el checklist o los documentos no pueden cargarse.

También se incluyen nuevamente los archivos base de la Fase 1 que requiere esta mejora:

- `web/app/common/__init__.py`
- `web/app/common/navigation.py`
- `web/app/services/documentos_laborales.py`

## Aplicación sugerida

Desde `/srv/rrhh_app`:

```bash
cp -a . ../rrhh_app_backup_antes_hotfix_fase1_checklist_$(date +%Y%m%d_%H%M%S)

unzip -o rrhh_app_hotfix_fase1_checklist_contrato.zip

docker compose up -d --build

docker compose exec web python -m compileall -q /app

docker compose logs --tail=120 web
```

## Validación

1. Abrir `/contratos/167` o cualquier contrato existente.
2. Confirmar que la pantalla carga sin error.
3. Revisar que aparece el bloque “Estado documental del contrato”.
4. Probar botón “Documentos” y “Generar contrato”.
