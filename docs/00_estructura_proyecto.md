# Sistema Grupo CS - Estructura del Proyecto

## 1. Descripción general

Sistema ERP interno para la gestión administrativa, documental y de recursos humanos del Grupo CS.

El sistema está desarrollado principalmente con:

- Python
- Flask
- SQLAlchemy
- PostgreSQL
- Docker Compose
- Jinja2
- Bootstrap

Su objetivo principal es centralizar procesos laborales, administrativos y documentales asociados a trabajadores, contratos, anexos, remuneraciones, solicitudes de fondos, rendiciones, egresos, vacaciones, certificados, reportes y futuros módulos operacionales.

---

## 2. Estructura principal

```text
/srv/rrhh_app
├── data/
├── docs/
├── migrations/
├── web/
├── .env
├── .env.example
├── .gitignore
└── docker-compose.yml
```

---

## 3. Directorios relevantes

### `web/`

Contiene la aplicación Flask.

```text
web/
├── app/
├── Dockerfile
├── requirements.txt
└── migrations/
```

### `web/app/`

Contiene el código principal del sistema.

```text
web/app/
├── blueprints/
├── document_templates/
├── models/
├── static/
├── templates/
├── utils.py
├── config.py
└── __init__.py
```

### `web/app/blueprints/`

Contiene los módulos funcionales del sistema.

Ejemplos:

- Trabajadores
- Contratos
- Anexos
- Desvinculaciones
- Finiquitos
- Sueldos
- Anticipos
- Solicitudes de fondos
- Rendiciones de gastos
- Vacaciones
- Egresos
- Certificados
- Dashboard
- Administración

---

## 4. Archivos de configuración

### `.env`

Archivo local con variables reales del ambiente. No debe versionarse.

### `.env.example`

Archivo de ejemplo sin credenciales reales. Sirve como plantilla para configurar nuevos ambientes.

### `docker-compose.yml`

Define los servicios principales:

- `db`: PostgreSQL
- `web`: Aplicación Flask/Gunicorn

---

## 5. Datos y volúmenes

### `data/db`

Contiene los datos reales de PostgreSQL cuando se usa el volumen local:

```yaml
./data/db:/var/lib/postgresql/data
```

Este directorio no debe eliminarse mientras sea usado por la base activa.

---

## 6. Respaldos

Los respaldos deben almacenarse fuera del código fuente, preferentemente en:

```text
/srv/backups/rrhh_app/
```

No se deben dejar respaldos `.sql`, `.dump`, `.tar.gz` o similares dentro del proyecto.

---

## 7. Convención general

El repositorio/proyecto debe contener:

- Código fuente
- Templates
- Migraciones
- Documentación
- Configuración base

No debe contener:

- Entornos virtuales
- Caché Python
- Backups sueltos
- Dumps de base de datos
- Archivos `.env` versionados
- Bases SQLite antiguas
- Archivos generados innecesarios
