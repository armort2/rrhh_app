# Fase 4 · Producto más escalable

## Objetivo
Refuerza la trazabilidad funcional y las pruebas mínimas de motores críticos sin modificar la estructura de base de datos.

## Componentes

### 1. Auditoría de negocio
Se agrega `audit_business_event()` sobre la tabla existente `audit_logs`, usando `event_type = business`.

Eventos inicialmente cubiertos:
- generación de contratos;
- generación de finiquitos;
- anulación de desvinculación;
- actualización de pago de finiquito.

### 2. Versionado del motor de finiquitos
`web/app/services/finiquitos_calc.py` expone:
- `FINIQUITO_ENGINE_VERSION`;
- `FINIQUITO_ENGINE_NAME`.

El resumen calculado incorpora esos datos en la llave `engine` y en `calculation_engine_version`.

### 3. Smoke tests
Se incorporan pruebas mínimas para:
- diferencia inclusiva de fechas;
- promedio de variables con formato chileno;
- base de feriado variable;
- existencia de versión de motor;
- navegación segura `safe_next_url`.

Comando recomendado dentro del contenedor:

```bash
docker compose exec web bash scripts/run_phase4_smoke_tests.sh
```

## Migraciones
No requiere migraciones.
