# Parche Fase 1 · Expediente documental

Este parche inicia la Fase 1 del roadmap de mejora del Sistema Grupo CS.

## Incluye

- Corrección de bug en creación manual de documentos por contrato.
- Helper global para redirecciones seguras `next` / `next_url`.
- Servicio transversal `documentos_laborales.py`.
- Registro automático de contratos generados en el expediente documental.
- Evento laboral automático al generar contrato.
- Nueva sección de checklist documental en el detalle del contrato.
- Inventario técnico actualizado.

## Aplicación recomendada en servidor

```bash
cd /srv/rrhh_app

cp -a . ../rrhh_app_backup_antes_fase1_expediente_$(date +%Y%m%d_%H%M%S)

unzip -o rrhh_app_patch_fase1_expediente_documental.zip

docker compose up -d --build

docker compose exec web flask db upgrade

docker compose exec web python -m compileall -q /app

docker compose logs --tail=120 web
```

## Validación funcional sugerida

1. Entrar a un contrato de prueba.
2. Revisar que aparezca el bloque “Estado documental del contrato”.
3. Generar contrato en formato DOCX.
4. Verificar que el contrato quede en Nextcloud.
5. Ir a “Documentos” del contrato y confirmar que aparece registrado.
6. Repetir con PDF o AMBOS.

## Rollback

```bash
cd /srv

docker compose -f rrhh_app/docker-compose.yml down

mv rrhh_app rrhh_app_fase1_fallida_$(date +%Y%m%d_%H%M%S)

mv rrhh_app_backup_antes_fase1_expediente_YYYYMMDD_HHMMSS rrhh_app

cd rrhh_app

docker compose up -d --build
```

Ajustar `YYYYMMDD_HHMMSS` al nombre real del respaldo creado.
