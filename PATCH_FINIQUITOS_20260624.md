# Parche finiquitos · feriado proporcional y vacaciones

## Objetivo
Corrige el asistente de cálculo de finiquitos para que el feriado proporcional sea consistente con el criterio operativo de la Dirección del Trabajo y con el caso de control:

- Inicio contrato: `2026-03-16`
- Término contrato: `2026-06-24`
- Sueldo base: `$553.553`
- Feriado registrado: `2026-06-29`
- Sin vacaciones tomadas

Resultado esperado:

- Tiempo servido: `0 años 3 meses 9 días`
- Días hábiles proporcionales: `4,13`
- Días inhábiles del período: `3,00`
- Días corridos equivalentes: `7,13`
- Feriado proporcional: `$131.561`
- Causal art. 160: sin aviso previo y sin años de servicio

## Archivos modificados

- `web/app/services/finiquitos_calc.py`
- `web/app/blueprints/desvinculaciones/routes.py`
- `web/app/templates/desvinculaciones/finiquito_generar.html`
- `web/app/static/js/desvinculaciones_finiquito_generar.js`

## Cambios principales

1. Reemplaza el cálculo `días * 15 / 365` por criterio mensual/fracción:
   - `15 / 12 = 1,25` días hábiles por mes.
   - `1,25 / 30` por día de fracción.
   - El período servido se calcula de forma inclusiva.

2. Reemplaza el factor fijo `1,4` por conteo real de días inhábiles:
   - Sábados.
   - Domingos.
   - Feriados activos registrados en el módulo de feriados.

3. Corrige el descuento de vacaciones usadas:
   - Los movimientos `USO` del módulo vacaciones se guardan negativos; ahora se descuentan como días positivos usados.
   - Se agrega respaldo desde comprobantes `Vacacion` en estado `EMITIDO` si por datos históricos no existe movimiento en `vacaciones_movimientos`.

4. Ajusta las indemnizaciones según causal:
   - Art. 160 / 159 / causales sin art. 161: no fuerza aviso previo ni años de servicio.
   - Art. 161 / necesidades de la empresa / desahucio: permite calcular aviso previo y años de servicio.

5. Mejora el modal del asistente:
   - Muestra período proporcional.
   - Muestra días inhábiles.
   - Muestra desglose de días usados desde movimientos y respaldo de comprobantes.
   - Aclara que la gratificación se considera para indemnizaciones, no para feriado proporcional.

## Aplicación sugerida

Desde `/srv/rrhh_app`:

```bash
cp -a web/app/services/finiquitos_calc.py web/app/services/finiquitos_calc.py.bak_$(date +%Y%m%d_%H%M%S)
cp -a web/app/blueprints/desvinculaciones/routes.py web/app/blueprints/desvinculaciones/routes.py.bak_$(date +%Y%m%d_%H%M%S)
cp -a web/app/templates/desvinculaciones/finiquito_generar.html web/app/templates/desvinculaciones/finiquito_generar.html.bak_$(date +%Y%m%d_%H%M%S)
cp -a web/app/static/js/desvinculaciones_finiquito_generar.js web/app/static/js/desvinculaciones_finiquito_generar.js.bak_$(date +%Y%m%d_%H%M%S)

unzip -o /ruta/al/parche_finiquitos_20260624.zip -d /srv/rrhh_app

docker compose restart web
docker compose logs -f --tail=80 web
```

No requiere migración de base de datos.
