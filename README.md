# Sistema RRHH – Grupo CS

Sistema interno de Gestión de Recursos Humanos (ERP RRHH) desarrollado para Grupo CS.

Plataforma orientada a centralizar, automatizar y auditar procesos laborales clave, construida con una arquitectura modular basada en Flask Blueprints, buenas prácticas de backend y un estándar visual corporativo.

---

## 🎯 Objetivo del sistema

Centralizar y automatizar procesos críticos del área de Recursos Humanos:

- Gestión de trabajadores
- Contratos y anexos (plazo fijo, extensión, indefinidos)
- Control de obras, cargos y horarios
- Inasistencias, anticipos y horas extras
- Generación de documentación laboral (PDF / DOCX)
- Administración de usuarios, roles y accesos

---

## 🧱 Stack tecnológico

- Lenguaje: Python 3.12
- Framework backend: Flask
- ORM: SQLAlchemy
- Base de datos: PostgreSQL / SQLite (desarrollo)
- Frontend: Jinja2 + Bootstrap 5
- Autenticación: Flask-Login
- Contenedores: Docker / Docker Compose
- Control de versiones: Git + GitHub

---

## 📁 Estructura del proyecto

Nota: el siguiente árbol está en formato “texto plano” deliberadamente para evitar problemas de renderizado.

    web/app/
    ├── __init__.py              # Factory create_app y registro de blueprints
    ├── config.py                # Configuración de entorno
    ├── extensions.py            # Inicialización de extensiones (DB, login, migrate)
    ├── models.py                # Modelos SQLAlchemy
    ├── utils.py                 # Utilidades compartidas (fechas, RUT, parseos)
    ├── cli.py                   # Comandos CLI personalizados
    │
    ├── auth/                    # Autenticación y autorización
    │   ├── routes.py
    │   └── decorators.py
    │
    ├── blueprints/              # Módulos funcionales (arquitectura principal)
    │   ├── core/
    │   ├── trabajadores/
    │   ├── contratos/
    │   ├── anexos/
    │   ├── anexos_indefinidos/
    │   ├── obras/
    │   ├── horarios/
    │   ├── anticipos/
    │   ├── horas_extras/
    │   ├── inasistencias/
    │   ├── admin/
    │   └── desvinculaciones/
    │
    ├── services/
    │   ├── anexos_extension_service.py
    │   └── desvinculaciones_docs.py
    │
    ├── templates/
    │   ├── base.html
    │   ├── index.html
    │   ├── cargos/
    │   ├── contratos/
    │   ├── anexos/
    │   ├── admin/
    │   └── print/
    │
    ├── static/
    │   ├── css/
    │   │   └── styles.css
    │   └── js/
    │
    └── document_templates/

---

## 🎨 Estándar visual

- Bootstrap 5 como base de UI
- CSS corporativo centralizado en `static/css/styles.css`
- No se utilizan estilos inline en templates finales
- Componentes y encabezados estandarizados:
  - `.section-header`
  - `.section-title`
  - `.section-subtitle`
  - `.section-divider`

Este estándar asegura **consistencia visual**, **mantenibilidad** y **facilidad de refactor**.

---

## 🏷️ Estados y badges

Criterio estándar de estados en el sistema:

- **VIGENTE** → badge verde  
- Otros estados → badge gris  

Ejemplo (Jinja2):

    {% if estado == "VIGENTE" %}
      <span class="badge text-bg-success">Vigente</span>
    {% else %}
      <span class="badge text-bg-secondary">{{ estado or "-" }}</span>
    {% endif %}

---

## 🔐 Seguridad y control de acceso

- Autenticación basada en **Flask-Login**
- Autorización por **roles**
- Control global de acceso mediante `before_request`
- Separación estricta entre:
  - rutas
  - servicios
  - templates
  - utilidades compartidas

---

## 🛠️ Entorno de desarrollo

### Construcción y ejecución

    docker compose build
    docker compose up -d

### Verificación rápida

    docker compose exec web bash -lc "python -c 'from app import create_app; create_app(); print(\"APP OK\")'"

---

## 📌 Estado del proyecto

- Proyecto activo
- Uso interno de Grupo CS
- Evolución modular por funcionalidades
- Versionado continuo y respaldo en GitHub

---

## 👤 Autor

**Armando Ortiz**  
Grupo CS – Sistemas y Recursos Humanos
