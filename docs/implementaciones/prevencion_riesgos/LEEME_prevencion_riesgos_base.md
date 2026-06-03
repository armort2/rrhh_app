# Paquete base - Módulo Prevención de Riesgos

Este paquete crea el esqueleto inicial del módulo de Prevención de Riesgos para Sistema Grupo CS.

## Instalación sugerida

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_base_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_riesgos.py
```

Validar sintaxis:

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/models/prevencion_riesgos.py \
  /app/app/blueprints/prevencion_riesgos/routes.py \
  /app/app/blueprints/prevencion_riesgos/queries.py \
  /app/app/blueprints/prevencion_riesgos/services.py \
  /app/app/blueprints/prevencion_riesgos/validators.py
```

Validar Flask:

```bash
docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY
```

Luego crear migración:

```bash
docker compose exec web flask db migrate -m "crear modulo prevencion riesgos"
```

Revisar migración antes de aplicar:

```bash
ls -lt web/migrations/versions | head
```

Aplicar migración:

```bash
docker compose exec web flask db upgrade
```
