# Parche finiquitos variables 2026-06-30

## Problema corregido

El asistente de cálculo de finiquito estaba tratando el tipo de remuneración `VARIABLE` como si reemplazara completamente al sueldo base.

Eso provocaba que, al ingresar sueldo base + variables de los últimos 3 meses, la base de cálculo quedara sólo con el promedio variable.

Ejemplo detectado:

- Sueldo base: $570.000
- Variable mes 1: $52.500
- Variable mes 2: $122.000
- Variable mes 3: $10.000
- Promedio variable: $61.500

Antes del parche:

- Base feriado: $61.500
- Base indemnización: $61.500

Después del parche:

- Base feriado: $631.500
- Base indemnización: $631.500, más gratificación/colación/movilización sólo si el usuario las marca cuando corresponda.

## Archivo modificado

- `web/app/services/finiquitos_calc.py`

## Regla aplicada

Para el uso real del sistema, `VARIABLE` y `MIXTA` se tratan como remuneración compuesta:

```text
sueldo base + promedio variables últimos 3 meses
```

La gratificación sigue excluida del feriado proporcional, y sólo se suma a la base indemnizatoria si se marca explícitamente en el asistente.

## Comandos sugeridos

```bash
cd /srv/rrhh_app

STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/parche_finiquitos_variables_$STAMP
cp -a web/app/services/finiquitos_calc.py backups/parche_finiquitos_variables_$STAMP/finiquitos_calc.py

unzip -o parche_finiquitos_variables_20260630.zip -d /srv/rrhh_app

docker compose exec -T web python -m py_compile app/services/finiquitos_calc.py

docker compose restart web
docker compose logs --tail=100 web
```

## Control rápido esperado

Con sueldo base $570.000 y variables $52.500 / $122.000 / $10.000:

```text
Promedio variable: $61.500
Base cálculo:      $631.500
Base indemnización:$631.500
```
