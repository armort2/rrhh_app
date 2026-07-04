# Fase 1 · Expediente documental y base de flujo unificado

Fecha: 2026-06-30  
Sistema: Grupo CS RRHH

## Objetivo

Iniciar la primera fase del roadmap de mejora del sistema, enfocada en estabilizar el módulo documental y dejar una base transversal para que los documentos generados por el sistema queden registrados automáticamente en el expediente laboral.

## Cambios incluidos

### 1. Corrección de bug en documentos por contrato

Archivo modificado:

- `web/app/blueprints/documentos/routes.py`

Se corrigió una referencia inválida a `documento.ruta_archivo` dentro de la ruta `nuevo_documento_contrato`. Esa variable no existía en el flujo de creación manual y podía provocar caída de la página al intentar registrar un nuevo documento.

También se normalizó la preselección de `tipo_documento` contra el catálogo `DOCUMENTO_TIPOS`.

### 2. Helper global para redirecciones seguras

Archivos nuevos/modificados:

- `web/app/common/navigation.py`
- `web/app/common/__init__.py`
- `web/app/auth/routes.py`
- `web/app/blueprints/trabajadores/routes.py`
- `web/app/blueprints/contratos/routes.py`

Se creó un helper común para validar parámetros `next` / `next_url` y evitar redirecciones abiertas hacia dominios externos.

Funciones principales:

- `is_safe_redirect_target(target)`
- `safe_next_url(target, fallback=None)`
- `safe_next_from_request(fallback=None, keys=("next", "next_url"))`

### 3. Servicio transversal de expediente documental

Archivo nuevo:

- `web/app/services/documentos_laborales.py`

Funciones principales:

- `register_generated_document(...)`
- `build_contract_document_checklist(contrato)`

Este servicio permite registrar documentos generados por el sistema en la tabla `documentos_laborales`, evitando duplicados por contrato/tipo/ruta.

### 4. Registro automático de contratos generados

Archivo modificado:

- `web/app/blueprints/contratos/routes.py`

Al generar un contrato en DOCX, PDF o ambos formatos, ahora el sistema:

1. Genera el archivo en Nextcloud como antes.
2. Registra el archivo en `documentos_laborales` como tipo `CONTRATOS`.
3. Crea un evento laboral de tipo `CONTRATO_GENERADO`.
4. Evita duplicar registros si se regenera el mismo archivo/ruta.

### 5. Detalle de contrato más útil

Archivo modificado:

- `web/app/templates/contratos/contrato_detalle.html`

Se agregó una sección superior con:

- Checklist documental del contrato.
- Estado de trabajador, RUT, empleador, obra/centro de costo, cargo, jornada, sueldo y documento registrado.
- Últimos documentos asociados al contrato.

Esto prepara la pantalla para evolucionar hacia el futuro “Contrato 360”.

### 6. Formulario manual de documentos

Archivo modificado:

- `web/app/templates/documentos/nuevo_documento_contrato.html`

Se preserva el parámetro `next` en el formulario para mejorar el retorno natural al flujo desde el cual se abrió la carga documental.

### 7. Inventario técnico actualizado

Archivo modificado:

- `docs/reportes_tecnicos/inventario_tecnico.md`

Se actualizó el inventario técnico para reflejar el estado real del proyecto, incluyendo blueprints nuevos, archivos JS, prevención de riesgos, reportería y el nuevo servicio documental.

## Pruebas realizadas

Se ejecutó compilación estática de Python:

```bash
python -m compileall -q web/app
```

Resultado: sin errores de sintaxis.

> Nota: no se ejecutaron pruebas con base de datos productiva ni generación real DOCX/PDF desde contenedor, por lo que se recomienda validar en el servidor con un contrato de prueba antes de uso masivo.

## Próximos pasos sugeridos

1. Probar generación de contrato DOCX, PDF y AMBOS con un contrato de prueba.
2. Confirmar que el documento aparece en “Documentos” del contrato.
3. Replicar el uso de `register_generated_document` en anexos individuales, certificados y cartas de aviso.
4. Crear el panel unificado “Prevalidar → Confirmar → Generar → Registrar → Abrir documento”.
