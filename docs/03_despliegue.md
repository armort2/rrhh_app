# Sistema Grupo CS - Procedimiento de Despliegue

## 1. Ubicación del proyecto

```bash
cd /srv/rrhh_app
```

---

## 2. Validar estado inicial

```bash
docker compose ps
docker compose logs --tail=80 web
docker compose exec web flask db current
```

---

## 3. Respaldo previo

Antes de desplegar cambios:

```bash
BACKUP_DIR="/srv/backups/rrhh_app/pre_deploy_$(date +%Y%m%d_%H%M)"
mkdir -p "$BACKUP_DIR"

docker compose exec db pg_dump -U rrhh_user rrhh_db > "$BACKUP_DIR/rrhh_db_pre_deploy.sql"

tar \
  --exclude='./.venv' \
  --exclude='./data/db' \
  --exclude='./**/__pycache__' \
  --exclude='./**/*.pyc' \
  --exclude='./*.sql' \
  --exclude='./*.dump' \
  -czf "$BACKUP_DIR/rrhh_app_codigo_pre_deploy.tar.gz" .
```

---

## 4. Aplicar cambios de código

Si los cambios se aplican manualmente, editar los archivos correspondientes.

Si se usa Git:

```bash
git pull
```

---

## 5. Reconstruir contenedor si cambian dependencias

Si cambia `requirements.txt`, `Dockerfile` o configuración base:

```bash
docker compose up -d --build
```

Si no cambian dependencias:

```bash
docker compose up -d
```

---

## 6. Aplicar migraciones

```bash
docker compose exec web flask db upgrade
```

---

## 7. Validaciones post-despliegue

```bash
docker compose ps

docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
print("DATABASE_URL detectada:", bool(app.config.get("SQLALCHEMY_DATABASE_URI")))
PY

docker compose exec web flask db current
docker compose logs --tail=100 web
```

---

## 8. Rollback básico

Si el despliegue falla:

1. Restaurar archivos desde respaldo de código.
2. Restaurar base de datos si hubo migraciones o cambios de datos.
3. Reiniciar contenedores.

Ejemplo de restauración de base:

```bash
cat /ruta/al/respaldo.sql | docker compose exec -T db psql -U rrhh_user -d rrhh_db
```

Usar con cuidado en producción.
