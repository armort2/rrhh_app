# Hotfix Fase 3 · Ajuste visual Cumplimiento Laboral

## Objetivo
Corregir detalles visuales del panel `/cumplimiento-laboral/`, especialmente textos largos que se salían de tarjetas o quedaban sin separación visual suficiente.

## Cambios incluidos
- Refuerzo de wrapping y ancho máximo en tarjetas del panel.
- Ajuste de acciones rápidas para separar claramente título y detalle.
- Corrección visual del listado "Puntos administrativos", evitando textos pegados al contador.
- Mejora de tablas y chips de obras para evitar desbordes.
- Mantiene la fase sin migraciones ni cambios de base de datos.

## Archivos modificados
- `web/app/templates/cumplimiento_laboral/index.html`
- `web/app/static/styles.css`
