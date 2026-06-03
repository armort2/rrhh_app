# Hotfix anticipos por contrato

Este hotfix elimina la restricción antigua `ux_anticipos_detalles_nomina_trabajador`, que impedía tener más de una línea por trabajador en una misma nómina, aunque correspondiera a contratos distintos.

Luego crea la regla correcta: una línea única por `nomina_id + contrato_id`.

Aplicar con:

```bash
docker compose exec -T db psql -U rrhh_user -d rrhh_db < web/app/sql/20260519_hotfix_anticipos_unique_por_contrato.sql
```
