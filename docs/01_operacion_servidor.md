# Sistema Grupo CS - Operación del Servidor

## 1. Ruta principal del sistema

```bash
/srv/rrhh_app
```

Para ubicarse en el proyecto:

```bash
cd /srv/rrhh_app
```

---

## 2. Contenedores Docker

El sistema utiliza Docker Compose.

Servicios principales:

- `rrhh_db`: Base de datos PostgreSQL.
- `rrhh_web`: Aplicación Flask servida con Gunicorn.

Ver estado:

```bash
docker compose ps
```

Levantar servicios:

```bash
docker compose up -d
```

Reiniciar servicios:

```bash
docker compose restart
```

Ver logs de la aplicación:

```bash
docker compose logs --tail=100 web
```

Ver logs de la base de datos:

```bash
docker compose logs --tail=100 db
```

---

## 3. Validar que Flask carga correctamente

```bash
docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
print("DATABASE_URL detectada:", bool(app.config.get("SQLALCHEMY_DATABASE_URI")))
PY
```

---

## 4. Validar migración actual

```bash
docker compose exec web flask db current
```

La salida esperada debe indicar la migración actual en `head`.

---

## 5. Aplicar migraciones

Antes de aplicar migraciones, siempre hacer respaldo de la base de datos.

Aplicar migraciones pendientes:

```bash
docker compose exec web flask db upgrade
```

Crear nueva migración:

```bash
docker compose exec web flask db migrate -m "descripcion_de_la_migracion"
```

---

## 6. Acceso a PostgreSQL

Entrar a `psql`:

```bash
docker compose exec db psql -U rrhh_user -d rrhh_db
```

---

## 7. Validaciones rápidas post-despliegue

Después de cambios importantes ejecutar:

```bash
docker compose ps
docker compose logs --tail=80 web
docker compose exec web flask db current
```

Validación Python:

```bash
docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("OK:", app.name)
PY
```
