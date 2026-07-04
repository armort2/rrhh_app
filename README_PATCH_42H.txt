Parche Horario Normal 42 horas - 2026-06-09

Aplicar desde /srv/rrhh_app:

1) Respaldar:
   cd /srv/rrhh_app
   BACKUP_DIR="respaldos_patch_horario_42h_$(date +%Y%m%d_%H%M%S)"
   mkdir -p "$BACKUP_DIR"
   cp -a web/app/blueprints/contratos/routes.py "$BACKUP_DIR/routes.py"
   cp -a web/app/static/js/contratos_form.js "$BACKUP_DIR/contratos_form.js"
   cp -a web/app/templates/contratos/nuevo_contrato.html "$BACKUP_DIR/nuevo_contrato.html"
   cp -a web/app/templates/contratos/contrato_editar.html "$BACKUP_DIR/contrato_editar.html"
   cp -a web/app/templates/horarios/horario_form.html "$BACKUP_DIR/horario_form.html"

2) Descomprimir el ZIP dentro de /srv/rrhh_app, reemplazando archivos.

3) Actualizar la base de datos. Opción recomendada si usan Flask-Migrate:
   docker compose exec web flask db upgrade

   Opción manual si prefieres ejecutar SQL directo:
   docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < web/app/sql/20260609_update_horario_normal_42_horas.sql

4) Reiniciar web:
   docker compose restart web

5) Verificar:
   - Admin > Horarios > Horario Normal
   - Nuevo contrato: horas semanales por defecto 42
   - Generar contrato con Horario Normal y Jornada texto vacía
