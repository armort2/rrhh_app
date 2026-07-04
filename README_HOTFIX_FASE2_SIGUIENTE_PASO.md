# Hotfix Fase 2 · Ajuste visual tarjeta "Siguiente paso"

## Objetivo
Mejorar el formato visual del bloque **Siguiente paso / Acciones sugeridas** en el detalle del contrato.

## Cambios incluidos
- Se ajusta el markup de cada acción sugerida para separar claramente:
  - ícono,
  - título,
  - detalle.
- Se refuerzan estilos CSS para evitar que el texto quede "pegado" o descuadrado.
- Se deja cada acción como un bloque de ancho completo, con mejor alineación vertical y wrapping de texto.

## Archivos modificados
- `web/app/templates/contratos/contrato_detalle.html`
- `web/app/static/styles.css`
