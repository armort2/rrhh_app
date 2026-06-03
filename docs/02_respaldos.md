# Sistema Grupo CS - Política de Respaldos

## 1. Ruta recomendada de respaldos

Los respaldos del sistema deben almacenarse fuera del código fuente:

```text
/srv/backups/rrhh_app/
```

---

## 2. Respaldo manual de base PostgreSQL

```bash
cd /srv/rrhh_app

BACKUP_DIR="/srv/backups/rrhh_app/manual_$(date +%Y%m%d_%H%M)"
mkdir -p "$BACKUP_DIR"

docker compose exec db pg_dump -U rrhh_user rrhh_db > "$BACKUP_DIR/rrhh_db.sql"

ls -lh "$BACKUP_DIR"
```

---

## 3. Respaldo manual del código

Este respaldo excluye archivos pesados o regenerables:

```bash
cd /srv/rrhh_app

BACKUP_DIR="/srv/backups/rrhh_app/manual_$(date +%Y%m%d_%H%M)"
mkdir -p "$BACKUP_DIR"

tar \
  --exclude='./.venv' \
  --exclude='./data/db' \
  --exclude='./**/__pycache__' \
  --exclude='./**/*.pyc' \
  --exclude='./*.sql' \
  --exclude='./*.dump' \
  -czf "$BACKUP_DIR/rrhh_app_codigo.tar.gz" .
```

---

## 4. Elementos que no deben quedar dentro del proyecto

No dejar dentro de `/srv/rrhh_app`:

- `.venv/`
- `__pycache__/`
- `*.pyc`
- `*.sql`
- `*.dump`
- `*.tar.gz`
- Bases SQLite antiguas
- Backups manuales sueltos

---

## 5. Validación de respaldos

Después de crear un respaldo:

```bash
ls -lh "$BACKUP_DIR"
```

Validar que el respaldo SQL no esté vacío:

```bash
wc -l "$BACKUP_DIR/rrhh_db.sql"
```

---

## 6. Recomendación operativa

Antes de cualquier cambio estructural, migración importante o refactor sensible:

1. Respaldar base de datos.
2. Respaldar código.
3. Confirmar que Docker está operativo.
4. Aplicar cambios.
5. Validar Flask.
6. Validar migraciones.
7. Revisar logs.
