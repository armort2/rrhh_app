# 2026-06-03 · Normalización global de botones y dropdowns · V5

## Versión

`2026.06.03-v5`

## Objetivo

Normalizar visualmente los botones y menús desplegables del Sistema Grupo CS sin intervenir uno por uno todos los templates.

## Cambios aplicados

- Se actualizó `VERSION` a `2026.06.03-v5`.
- Se actualizó el cache-buster del CSS en `base.html`.
- Se agregó un bloque CSS transversal para botones Bootstrap:
  - `btn-primary`
  - `btn-secondary`
  - `btn-success`
  - `btn-warning`
  - `btn-danger`
  - `btn-info`
  - variantes `btn-outline-*`
- Se normalizó el comportamiento visual de dropdowns globales.
- Se reforzó el `z-index` y `overflow` para menús abiertos dentro de tarjetas, tablas, fichas, formularios y navbar.

## Archivos modificados

- `VERSION`
- `web/app/templates/base.html`
- `web/app/static/styles.css`

## Nota operativa

Después de aplicar el parche se recomienda recargar el navegador con `Ctrl + F5` para evitar CSS en caché.
