# Sistema Grupo CS - Estándar Técnico

## 1. Objetivo

Este documento define criterios técnicos básicos para mantener el Sistema Grupo CS ordenado, mantenible y preparado para crecer.

El sistema debe evolucionar priorizando:

- Claridad.
- Trazabilidad.
- Reutilización de código.
- Seguridad operacional.
- Cumplimiento laboral chileno.
- Consistencia visual y funcional.

---

## 2. Principio general

Los nuevos módulos deben construirse con una estructura más ordenada que los módulos históricos.

Cuando se modifique un módulo antiguo, se recomienda mejorar gradualmente su estructura, sin hacer refactors masivos innecesarios.

---

## 3. Estructura recomendada para nuevos módulos

Cada nuevo blueprint debería usar una estructura similar a:

```text
web/app/blueprints/nombre_modulo/
├── __init__.py
├── routes.py
├── services.py
├── queries.py
├── validators.py
└── constants.py
```

Cuando el módulo sea pequeño, algunos archivos pueden omitirse, pero se recomienda evitar que `routes.py` concentre toda la lógica.

---

## 4. Responsabilidades sugeridas

### `routes.py`

Debe encargarse principalmente de:

- Recibir request.
- Validar permisos básicos.
- Llamar servicios o queries.
- Renderizar templates.
- Redirigir o devolver respuestas.

No debería concentrar cálculos extensos ni lógica documental pesada.

### `services.py`

Debe contener lógica de negocio:

- Cálculos.
- Generación de documentos.
- Procesos transaccionales.
- Cambios de estado.
- Reglas funcionales.

### `queries.py`

Debe contener consultas complejas o reutilizables.

### `validators.py`

Debe contener validaciones funcionales.

### `constants.py`

Debe contener catálogos internos, estados, tipos y valores fijos del módulo.

---

## 5. Helpers comunes

Los helpers transversales deben ubicarse en:

```text
web/app/common/
```

Actualmente existen:

```text
web/app/common/rut.py
web/app/common/money.py
web/app/common/dates.py
```

---

## 6. Uso recomendado de helpers

Para RUT:

```python
from app.common.rut import rut_con_puntos, rut_compacto, rut_plano, is_valid_rut
```

Para montos:

```python
from app.common.money import money_to_int, money_to_decimal, format_clp, format_clp_plain
```

Para fechas:

```python
from app.common.dates import parse_date, format_date_cl, format_date_iso, format_date_long_es, add_months
```

---

## 7. Regla para módulos antiguos

No se deben reemplazar todos los helpers antiguos de una sola vez.

La estrategia recomendada es:

1. Crear helpers oficiales.
2. Usarlos en módulos nuevos.
3. Migrar módulos antiguos solo cuando se intervengan por mantención o mejora.
4. Validar Flask y migraciones después de cada cambio.

---

## 8. Templates

Los templates nuevos deben mantener el estándar corporativo:

- Jinja2.
- Bootstrap.
- Grilla `row` / `col`.
- Formularios ordenados por secciones.
- Evitar estilo tipo formulario genérico.
- Evitar exceso de estilos inline.
- Separar JavaScript cuando sea razonable.

---

## 9. Componentes Jinja sugeridos

Se recomienda crear componentes reutilizables en:

```text
web/app/templates/components/
```

Componentes sugeridos:

- `page_header.html`
- `kpi_card.html`
- `filter_panel.html`
- `status_badge.html`
- `empty_state.html`
- `form_section.html`
- `action_bar.html`
- `confirm_modal.html`

---

## 10. JavaScript

Actualmente el sistema no cuenta con archivos JS propios centralizados.

Para nuevas funcionalidades se recomienda usar:

```text
web/app/static/js/
```

Archivos sugeridos a futuro:

- `app.js`
- `forms.js`
- `filters.js`
- `tables.js`
- `dashboards.js`

---

## 11. Modelos

Los modelos nuevos deben crearse preferentemente en archivos separados dentro de:

```text
web/app/models/
```

Ejemplo:

```text
web/app/models/prevencion_riesgos.py
```

Luego deben exponerse desde:

```text
web/app/models/__init__.py
```

Esto permite migrar gradualmente desde `models_legacy.py`.

---

## 12. Validaciones obligatorias después de cambios

Después de cambios técnicos relevantes ejecutar:

```bash
docker compose exec -T web python3 - <<'PY'
from app import create_app
app = create_app()
print("App Flask carga correctamente:", app.name)
PY

docker compose exec web flask db current
```

Si se modifican archivos Python específicos:

```bash
docker compose exec -T web python3 -m py_compile /app/app/ruta/al/archivo.py
```

---

## 13. Respaldos

Antes de cambios estructurales, migraciones o refactors sensibles:

1. Respaldar base de datos.
2. Respaldar código.
3. Aplicar cambios.
4. Validar app.
5. Revisar logs.

La ruta institucional de respaldos es:

```text
/srv/backups/rrhh_app/
```

---

## 14. Módulo Prevención de Riesgos

El módulo de Prevención de Riesgos debe nacer usando este estándar técnico.

Se recomienda que incluya desde el inicio:

- Modelos separados.
- Blueprint propio.
- Templates propios.
- Helpers comunes.
- Servicios de negocio.
- Queries separadas si las consultas crecen.
- Componentes visuales reutilizables.

---

## 15. Alcance MVP sugerido para Prevención de Riesgos

Para una primera etapa, se recomienda partir con:

```text
Prevención de Riesgos
├── Dashboard preventivo
├── Matriz de trabajadores por obra
├── Entrega de EPP
├── Charlas de seguridad
├── Documentos preventivos
└── Alertas de vencimientos
```

Para una segunda etapa, se puede considerar:

```text
Prevención de Riesgos - Etapa 2
├── Incidentes / accidentes
├── Investigación de accidentes
├── Comité Paritario
├── Exámenes ocupacionales avanzados
└── Capacitaciones externas
```

---

## 16. Criterio de crecimiento

El sistema debe crecer de forma incremental.

Antes de incorporar funcionalidades grandes, se recomienda definir:

- Modelo de datos.
- Permisos.
- Estados.
- Flujo operativo.
- Templates base.
- Reportes necesarios.
- Documentos a generar.
- Alertas o vencimientos.
- Relación con trabajadores, obras, empleadores y cargos.

---

## 17. Validación visual

Las vistas nuevas deben revisarse considerando:

- Orden visual.
- Claridad de filtros.
- Botones agrupados.
- Estados visibles.
- Formularios por secciones.
- Compatibilidad con el estilo corporativo existente.
- Uso correcto de Bootstrap.
- Evitar pantallas tipo formulario genérico.

---

## 18. Criterio de no regresión

Cada cambio debe procurar no afectar módulos existentes.

Después de cada intervención relevante se recomienda validar:

```bash
docker compose ps
docker compose logs --tail=80 web
docker compose exec web flask db current
```

Y, cuando corresponda, probar manualmente:

- Login.
- Listado de trabajadores.
- Ficha de trabajador.
- Contratos.
- Anexos.
- Sueldos.
- Solicitudes de fondos.
- Rendiciones.
- Módulo intervenido.

---

## 19. Convención de trabajo

Para mantener el sistema ordenado:

- No dejar archivos con nombres como `copia`, `backup`, `old`, `eliminar` dentro del código activo.
- Mover archivos históricos a `/srv/backups/rrhh_app/`.
- No guardar dumps SQL dentro del proyecto.
- No subir `.env` a repositorio.
- No usar `.venv` dentro del proyecto en producción.
- Usar Docker como entorno principal de ejecución.
- Documentar cambios estructurales en `docs/`.

---

## 20. Conclusión

Este estándar busca que el Sistema Grupo CS evolucione como una plataforma institucional, mantenible y preparada para nuevos módulos.

El módulo de Prevención de Riesgos debe servir como referencia para construir funcionalidades nuevas con mejor estructura, menor duplicidad y mayor trazabilidad.
