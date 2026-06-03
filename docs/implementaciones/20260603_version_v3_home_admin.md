# Implementación 2026-06-03 · Versión v3, navbar Admin y limpieza de inicio

## Objetivo

Corregir la lectura de versión institucional y ordenar los accesos administrativos para evitar duplicidad entre la página inicial y el navbar.

## Cambios aplicados

- Se actualizó `VERSION` a `2026.06.03-v3`.
- Se hizo robusta la lectura de versión en `web/app/__init__.py`, buscando el archivo `VERSION` desde la ubicación real del paquete Flask hacia arriba en el árbol del proyecto.
- Se agregó `Cargos` al menú `Admin` del navbar.
- Se incluyó `/cargos` dentro de la detección de estado activo del menú `Admin`.
- Se eliminó la tarjeta `Administración` de la página inicial para evitar duplicidad con el navbar.
- Se amplió la tarjeta `Prevención de Riesgos` en el bloque inferior del inicio para conservar una grilla visual ordenada.

## Criterio

El panel inicial queda enfocado en operación diaria y módulos funcionales. La administración del sistema queda centralizada en `Admin`, que es el lugar más coherente para catálogos, parámetros, usuarios, horarios, feriados, cargos y salud del sistema.
