# Prevención de Riesgos - Base contractual

Este paquete aplica la primera fase para que el módulo de Prevención de Riesgos pueda operar por contrato laboral.

## Cambios incluidos

### Modelo

Actualiza:

- `web/app/models/prevencion_riesgos.py`

Agrega `contrato_id` nullable y relación `contrato` en:

- `PrevEntregaEPP`
- `PrevDocumentoPreventivo`
- `PrevCharlaAsistente`

La charla sigue siendo un evento de obra, pero cada asistente puede quedar vinculado a un contrato específico.

### Migración

Agrega:

- `web/migrations/versions/6c2a9f4e8b71_agregar_contrato_id_prevencion_riesgos.py`

La migración:

- Agrega `contrato_id` a `prev_entregas_epp`.
- Agrega `contrato_id` a `prev_documentos_preventivos`.
- Agrega `contrato_id` a `prev_charla_asistentes`.
- Crea índices.
- Crea FK hacia `contratos.id` con `ON DELETE SET NULL`.
- Cambia la unique constraint de asistentes de charla:
  - Antes: `(charla_id, trabajador_id)`
  - Ahora: `(charla_id, trabajador_id, contrato_id)`

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_contrato_base_grupo_cs.zip -d /srv/rrhh_app
```

## Validación previa

```bash
docker compose exec -T web python3 -m py_compile \
  /app/app/models/prevencion_riesgos.py \
  /app/migrations/versions/6c2a9f4e8b71_agregar_contrato_id_prevencion_riesgos.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY
```

## Aplicar migración

```bash
docker compose exec web flask db upgrade
docker compose exec web flask db current
```

## Verificación en PostgreSQL

```bash
docker compose exec db psql -U rrhh_user -d rrhh_db -c "\d prev_documentos_preventivos"
docker compose exec db psql -U rrhh_user -d rrhh_db -c "\d prev_entregas_epp"
docker compose exec db psql -U rrhh_user -d rrhh_db -c "\d prev_charla_asistentes"
```

## Nota importante

Esta fase solo agrega soporte estructural para `contrato_id`.

Los formularios seguirán funcionando como hasta ahora. En una fase posterior se ajustarán para seleccionar contrato y derivar desde ahí trabajador, obra, cargo y empleador.
