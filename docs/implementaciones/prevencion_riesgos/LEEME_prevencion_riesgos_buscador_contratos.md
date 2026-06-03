# Prevención de Riesgos - Buscador inteligente de trabajador/contrato

Este paquete mejora la selección de trabajador/contrato en formularios preventivos.

## Objetivo

Evitar cargar todos los trabajadores/contratos en selects gigantes y reemplazarlos por un buscador dinámico.

Permite buscar por:

- nombres
- apellido paterno
- apellido materno
- RUT con o sin puntos/guion
- ID de contrato

## Archivos incluidos

- `web/app/common/trabajadores.py`
- `scripts/patch_prevencion_buscador_contratos.py`
- `web/app/templates/prevencion_riesgos/epp_form.html`
- `web/app/templates/prevencion_riesgos/documento_form.html`
- `web/app/templates/prevencion_riesgos/charla_form.html`

## Nueva ruta API

El script agrega:

```text
GET /prevencion-riesgos/api/contratos?q=texto
```

Devuelve contratos vigentes filtrados por permisos de obra del usuario.

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_buscador_contratos_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_buscador_contratos.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/common/trabajadores.py \
  /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep api/contratos
```

## Reinicio

```bash
docker compose restart web
```

## Prueba

Abrir y probar búsquedas:

- `/prevencion-riesgos/epp/nueva`
- `/prevencion-riesgos/documentos/nuevo`
- `/prevencion-riesgos/charlas/nueva`

Buscar por:

- apellido paterno
- apellido materno
- nombre
- RUT
- ID contrato

## Nota técnica

El helper común queda en `app.common.trabajadores`, por lo que después podemos reutilizarlo en otros módulos del sistema que necesiten buscar trabajador/contrato.
