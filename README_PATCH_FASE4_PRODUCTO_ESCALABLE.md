# Patch Fase 4 · Producto más escalable

## Objetivo
Reforzar el sistema como producto interno más robusto, trazable y mantenible, sin agregar migraciones ni modificar estructura de base de datos.

## Cambios incluidos

### 1. Auditoría de negocio
Se agrega `audit_business_event()` en `web/app/services/audit.py`, reutilizando la tabla existente `audit_logs` con `event_type = business`.

Eventos cubiertos en esta primera iteración:
- contrato generado;
- finiquito generado;
- desvinculación anulada;
- control de pago de finiquito actualizado.

La pantalla `Admin > Auditoría` ahora muestra:
- total de eventos de negocio de los últimos 7 días;
- acciones de negocio frecuentes de los últimos 30 días;
- filtro por evento `Negocio`.

### 2. Versionado de motor de finiquitos
El motor `web/app/services/finiquitos_calc.py` ahora expone:
- `FINIQUITO_ENGINE_NAME`;
- `FINIQUITO_ENGINE_VERSION`.

El resumen del cálculo incorpora:
- `engine.name`;
- `engine.version`;
- `engine.generated_at`;
- `calculation_engine_version`.

Esto permite saber con qué versión lógica se calculó un finiquito guardado en `meta`.

### 3. Smoke tests técnicos
Se agregan pruebas mínimas dentro del build web:

- `web/tests/test_finiquitos_calc.py`
- `web/tests/test_navigation.py`
- `web/scripts/run_phase4_smoke_tests.sh`

Comando recomendado después del build:

```bash
docker compose exec web bash scripts/run_phase4_smoke_tests.sh
```

## Archivos modificados
- `web/app/services/audit.py`
- `web/app/services/finiquitos_calc.py`
- `web/app/blueprints/contratos/routes.py`
- `web/app/blueprints/desvinculaciones/routes.py`
- `web/app/blueprints/admin/routes.py`
- `web/app/templates/admin/auditoria.html`
- `web/app/static/styles.css`

## Archivos nuevos
- `web/tests/__init__.py`
- `web/tests/test_finiquitos_calc.py`
- `web/tests/test_navigation.py`
- `web/scripts/run_phase4_smoke_tests.sh`
- `docs/implementaciones/20260701_fase4_producto_escalable.md`

## Migraciones
No requiere migraciones.
