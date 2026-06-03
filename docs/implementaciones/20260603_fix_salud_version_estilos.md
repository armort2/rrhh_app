# Fix panel Salud del sistema · versión y estilos

## Correcciones

- La versión del sistema ahora se lee prioritariamente desde el archivo `VERSION`.
- Se evita mostrar `vdev` cuando el entorno Docker tenga `SYSTEM_VERSION=dev`.
- Se reserva `SYSTEM_VERSION_OVERRIDE` para forzar una versión puntual de manera explícita.
- El template `admin/salud_sistema.html` fue alineado al estándar visual corporativo usado en el resto del sistema: `container-fluid`, `section-header`, tarjetas Bootstrap y estilos del tema Grupo CS.
- Se reforzaron los estilos CSS específicos del panel de salud.

## Ruta

`/admin/salud-sistema`
