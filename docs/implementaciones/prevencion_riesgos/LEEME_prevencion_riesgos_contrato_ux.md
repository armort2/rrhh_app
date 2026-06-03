# Prevención de Riesgos - Selección por Contrato en Formularios

Este paquete implementa la segunda fase contractual del módulo preventivo.

## Objetivo

Cambiar la UX para que EPP, Documentos y Charlas trabajen con el contrato específico del trabajador.

## Cambios incluidos

### Script

- `scripts/patch_prevencion_contrato_ux.py`

Actualiza `routes.py` para:

- Importar `Contrato`.
- Agregar helpers contractuales.
- Pasar contratos vigentes a formularios.
- Persistir `contrato_id` en:
  - `PrevEntregaEPP`
  - `PrevDocumentoPreventivo`
  - `PrevCharlaAsistente`

### Templates

- `web/app/templates/prevencion_riesgos/epp_form.html`
- `web/app/templates/prevencion_riesgos/documento_form.html`
- `web/app/templates/prevencion_riesgos/charla_form.html`

## Comportamiento

### EPP y Documentos

Seleccionan contrato y derivan:

- trabajador_id
- obra_id

### Charlas

La charla sigue siendo evento de obra, pero los asistentes se seleccionan por contrato:

- contrato_id
- trabajador_id derivado desde contrato

## Instalación

Desde `/srv/rrhh_app`:

```bash
unzip -o prevencion_riesgos_contrato_ux_grupo_cs.zip -d /srv/rrhh_app
python3 scripts/patch_prevencion_contrato_ux.py
```

## Validación

```bash
docker compose exec -T web python3 -m py_compile /app/app/blueprints/prevencion_riesgos/routes.py

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec -T web flask routes | grep prevencion
```

## Reinicio

```bash
docker compose restart web
```

## Verificación en BD

```bash
docker compose exec db psql -U rrhh_user -d rrhh_db -c "select id, contrato_id, trabajador_id, obra_id from prev_entregas_epp order by id desc limit 10;"
docker compose exec db psql -U rrhh_user -d rrhh_db -c "select id, contrato_id, trabajador_id, obra_id from prev_documentos_preventivos order by id desc limit 10;"
docker compose exec db psql -U rrhh_user -d rrhh_db -c "select id, charla_id, contrato_id, trabajador_id from prev_charla_asistentes order by id desc limit 10;"
```
