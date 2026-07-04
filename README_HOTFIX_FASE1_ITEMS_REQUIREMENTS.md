# Hotfix Fase 1 · Checklist contrato + requirements

Fecha: 2026-06-30

## Objetivo

Corrige dos incidencias detectadas al aplicar la Fase 1 de expediente documental:

1. **Error Jinja en detalle de contrato**
   - Problema: `documento_checklist.items` era interpretado por Jinja como el método nativo `dict.items`, no como la llave `"items"` del diccionario.
   - Síntoma: `TypeError: 'builtin_function_or_method' object is not iterable` al abrir `/contratos/<id>`.
   - Solución: el template ahora usa `documento_checklist_items` y accesos seguros mediante `.get()`.

2. **Error de rebuild Docker por dependencias `zip` / `unzip` de PyPI**
   - Problema: `requirements.txt` incluía `zip` y `unzip`. El paquete `zip` arrastra dependencias antiguas incompatibles con Python 3.12, como `wsgiref` con sintaxis Python 2.
   - Síntoma: falla en `RUN pip install --no-cache-dir -r requirements.txt`.
   - Solución: se eliminan `zip` y `unzip` de `web/requirements.txt`. Para generar ZIPs el sistema usa `zipfile`, que pertenece a la biblioteca estándar de Python.

## Archivos incluidos

- `web/app/templates/contratos/contrato_detalle.html`
- `web/app/blueprints/contratos/routes.py`
- `web/app/common/__init__.py`
- `web/app/common/navigation.py`
- `web/app/services/documentos_laborales.py`
- `web/requirements.txt`
- `docs/implementaciones/20260630_fase1_expediente_documental.md`
- `docs/reportes_tecnicos/inventario_tecnico.md`

## Aplicación sugerida

```bash
cd /srv/rrhh_app

cp -a . ../rrhh_app_backup_antes_hotfix_fase1_items_requirements_$(date +%Y%m%d_%H%M%S)

unzip -o rrhh_app_hotfix_fase1_items_requirements.zip

docker compose build --no-cache web

docker compose up -d

docker compose exec web python -m compileall -q /app

docker compose logs --tail=120 web
```

## Validación

Abrir:

```text
/contratos/167
```

Debe cargar sin error 500 y mostrar el bloque `Estado documental del contrato`.
