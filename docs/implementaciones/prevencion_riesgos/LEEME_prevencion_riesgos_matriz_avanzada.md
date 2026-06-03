# Prevención de Riesgos - Matriz Preventiva Avanzada

Este paquete mejora la matriz preventiva para transformarla en un semáforo operativo real.

## Cambios incluidos

- Matriz ordenada por criticidad.
- Estado general:
  - Al día
  - Observación
  - Crítico
- Control por trabajador de:
  - ODI
  - Entrega EPP
  - Charla reciente últimos 30 días
  - Documentos vencidos
  - Documentos por vencer
  - Reposiciones EPP vencidas
  - Reposiciones EPP por vencer

## Archivos modificados

- `web/app/blueprints/prevencion_riesgos/queries.py`
- `web/app/templates/prevencion_riesgos/matriz.html`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_matriz_avanzada_grupo_cs.zip -d /srv/rrhh_app
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/queries.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose restart web
```

## Prueba

Abrir:

```text
https://sistema.grupo-cs.cl/prevencion-riesgos/matriz
```
