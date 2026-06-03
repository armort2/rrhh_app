# Prevención de Riesgos - Matriz preventiva por contrato

Este paquete convierte la matriz preventiva para que evalúe contratos vigentes en vez de trabajadores.

## Cambios incluidos

- `web/app/blueprints/prevencion_riesgos/queries.py`
- `web/app/templates/prevencion_riesgos/matriz.html`
- `scripts/patch_prevencion_matriz_por_contrato.py`

## Qué mejora

La matriz ahora trabaja por `contrato_id`.

Esto evita que un trabajador con dos contratos quede marcado como "al día" por información preventiva de otro contrato.

## Filtros agregados

- Empresa / empleador
- Obra
- Buscador de trabajador / RUT / ID de contrato

El buscador usa lógica flexible con `unaccent`, por lo que acepta búsquedas con o sin tildes.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_matriz_por_contrato_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_matriz_por_contrato.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/blueprints/prevencion_riesgos/queries.py \
  /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY
```

## Reinicio

```bash
docker compose restart web
```

## Prueba

Abrir:

```text
/prevencion-riesgos/matriz
```

Probar filtros por:

- Empresa
- Obra
- Apellidos
- Nombre
- RUT
- ID de contrato
