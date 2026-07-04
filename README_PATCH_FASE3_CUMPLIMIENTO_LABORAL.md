# Parche Fase 3 · Cumplimiento Laboral

## Qué agrega
- Nuevo panel de cumplimiento laboral.
- Alertas ejecutivas sobre contratos, jornada, sueldo mínimo, parámetros y prevención.
- Acciones rápidas hacia parámetros laborales, anexos masivos, prevención y Ley Karin.
- Checklist inicial Ley Karin sin migraciones.

## Comandos
```bash
cd /srv/rrhh_app
cp -a . ../rrhh_app_backup_antes_fase3_cumplimiento_$(date +%Y%m%d_%H%M%S)
unzip -o rrhh_app_patch_fase3_cumplimiento_laboral.zip
docker compose up -d --build
docker compose exec web python -m compileall -q /app
docker compose logs --tail=120 web
```

## Validación
```bash
docker compose exec web flask routes | grep cumplimiento
```

Abrir:
- `/cumplimiento-laboral/`
- `/cumplimiento-laboral/ley-karin`

No incluye migraciones de base de datos.
