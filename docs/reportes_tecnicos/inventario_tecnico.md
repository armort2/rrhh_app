# Sistema Grupo CS - Inventario Técnico

Reporte actualizado para el parche Fase 1 de expediente documental.

## 1. Resumen general

- Archivos totales versionables detectados: 443
- Archivos Python: 133
- Templates HTML/Jinja: 167
- Archivos CSS: 1
- Archivos JS: 38
- Plantillas DOCX: 23
- Documentos Markdown: 35
- Blueprints con carpeta propia: 33

## 2. Blueprints detectados

- `acuerdos_pago` — Python: 2, templates asociados: 3
- `admin` — Python: 2, templates asociados: 5
- `anexos` — Python: 2, templates asociados: 5
- `anexos_cambio_cargo` — Python: 2, templates asociados: 4
- `anexos_cambio_sueldo` — Python: 2, templates asociados: 4
- `anexos_indefinidos` — Python: 2, templates asociados: 6
- `anexos_masivos` — Python: 2, templates asociados: 5
- `anticipos` — Python: 2, templates asociados: 8
- `certificados` — Python: 2, templates asociados: 4
- `contratos` — Python: 2, templates asociados: 5
- `contratos_vencimientos` — Python: 2, templates asociados: 1
- `core` — Python: 2, templates asociados: 0
- `dashboard` — Python: 2, templates asociados: 3
- `desvinculaciones` — Python: 2, templates asociados: 6
- `documentos` — Python: 2, templates asociados: 4
- `egresos` — Python: 2, templates asociados: 3
- `extras_remuneracion` — Python: 2, templates asociados: 3
- `feriados` — Python: 2, templates asociados: 2
- `horarios` — Python: 2, templates asociados: 2
- `horas_extras` — Python: 2, templates asociados: 8
- `inasistencias` — Python: 2, templates asociados: 4
- `obras` — Python: 2, templates asociados: 3
- `pago_proveedores` — Python: 2, templates asociados: 6
- `parametros_laborales` — Python: 2, templates asociados: 3
- `prevencion_riesgos` — Python: 6, templates asociados: 15
- `rendiciones_gastos` — Python: 2, templates asociados: 6
- `reporteria` — Python: 2, templates asociados: 10
- `solicitudes_fondos` — Python: 2, templates asociados: 10
- `sueldos` — Python: 1, templates asociados: 5
- `terceros` — Python: 2, templates asociados: 5
- `trabajadores` — Python: 3, templates asociados: 4
- `transferencias_bancarias` — Python: 2, templates asociados: 2
- `vacaciones` — Python: 2, templates asociados: 4

## 3. Archivos Python más grandes

| Archivo | Líneas | KB |
|---|---:|---:|
| `web/app/blueprints/solicitudes_fondos/routes.py` | 3071 | 111.6 |
| `web/app/models_legacy.py` | 2320 | 86.7 |
| `web/app/blueprints/anticipos/routes.py` | 2275 | 79.0 |
| `web/app/blueprints/desvinculaciones/routes.py` | 2098 | 70.2 |
| `web/app/blueprints/rendiciones_gastos/routes.py` | 1686 | 52.3 |
| `web/app/blueprints/horas_extras/routes.py` | 1520 | 52.5 |
| `web/app/blueprints/trabajadores/routes.py` | 1484 | 56.5 |
| `web/app/services/anexos_masivos.py` | 1237 | 42.6 |
| `web/app/blueprints/vacaciones/routes.py` | 1200 | 39.8 |
| `web/app/blueprints/dashboard/routes.py` | 1156 | 38.3 |
| `web/app/blueprints/sueldos/routes.py` | 1132 | 37.6 |
| `web/app/blueprints/reporteria/routes.py` | 1111 | 45.1 |
| `web/app/blueprints/prevencion_riesgos/routes.py` | 1086 | 37.0 |
| `web/app/blueprints/contratos/routes.py` | 980 | 37.1 |
| `web/app/cli.py` | 886 | 33.8 |
| `web/app/blueprints/extras_remuneracion/routes.py` | 873 | 28.5 |
| `web/app/services/bank_nominas.py` | 871 | 33.3 |
| `web/app/blueprints/inasistencias/routes.py` | 791 | 25.3 |
| `web/app/services/desvinculaciones_docs.py` | 761 | 25.9 |
| `web/app/services/docx_engine.py` | 727 | 22.1 |
| `web/app/blueprints/anexos_indefinidos/routes.py` | 671 | 22.9 |
| `web/app/services/finiquitos_calc.py` | 652 | 21.8 |
| `web/app/blueprints/acuerdos_pago/routes.py` | 638 | 20.5 |
| `web/app/blueprints/pago_proveedores/routes.py` | 617 | 20.4 |
| `web/app/blueprints/certificados/routes.py` | 569 | 17.6 |

## 4. Templates HTML/Jinja más grandes

| Template | Líneas | KB |
|---|---:|---:|
| `web/app/templates/trabajadores/trabajador_detalle.html` | 1180 | 54.4 |
| `web/app/templates/solicitudes_fondos/detalle.html` | 1005 | 50.3 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_imprimir_pdf.html` | 662 | 20.4 |
| `web/app/templates/trabajadores/trabajador_editar.html` | 569 | 28.6 |
| `web/app/templates/anticipos/anticipos_detalle.html` | 566 | 21.9 |
| `web/app/templates/rendiciones_gastos/detalle.html` | 559 | 24.3 |
| `web/app/templates/trabajadores/nuevo_trabajador.html` | 558 | 27.9 |
| `web/app/templates/dashboard/solicitudes_fondos.html` | 551 | 21.0 |
| `web/app/templates/desvinculaciones/finiquito_generar.html` | 547 | 25.1 |
| `web/app/templates/base.html` | 546 | 32.6 |
| `web/app/templates/anexos_masivos/detalle.html` | 530 | 21.5 |
| `web/app/templates/extras_remuneracion/lote_detalle.html` | 485 | 22.1 |
| `web/app/templates/contratos_vencimientos/listado.html` | 457 | 20.9 |
| `web/app/templates/dashboard/personal_mes.html` | 407 | 15.7 |
| `web/app/templates/sueldos/sueldos_detalle.html` | 368 | 15.5 |
| `web/app/templates/desvinculaciones/desvinculaciones_listado.html` | 355 | 14.7 |
| `web/app/templates/contratos/contrato_generar.html` | 350 | 12.4 |
| `web/app/templates/horas_extras/revision_remu.html` | 338 | 15.8 |
| `web/app/templates/contratos/contratos.html` | 337 | 15.2 |
| `web/app/templates/inasistencias/revision.html` | 334 | 14.9 |
| `web/app/templates/dashboard/bienestar.html` | 333 | 12.3 |
| `web/app/templates/contratos/contrato_detalle.html` | 333 | 15.3 |
| `web/app/templates/parametros_laborales/form.html` | 327 | 11.9 |
| `web/app/templates/contratos/contrato_editar.html` | 308 | 13.7 |
| `web/app/templates/inasistencias/listado.html` | 299 | 12.4 |

## 5. Archivos estáticos


### CSS

- `web/app/static/styles.css` — 3833 líneas, 93.2 KB

### JS

- `web/app/static/js/acuerdos_pago_form.js` — 187 líneas, 5.7 KB
- `web/app/static/js/anexos_cambio_cargo_form.js` — 43 líneas, 1.2 KB
- `web/app/static/js/anexos_cambio_sueldo_form.js` — 87 líneas, 2.4 KB
- `web/app/static/js/anexos_extension_nuevo.js` — 60 líneas, 1.7 KB
- `web/app/static/js/anexos_indefinidos_generar.js` — 18 líneas, 0.6 KB
- `web/app/static/js/anexos_masivos_detalle.js` — 32 líneas, 1.3 KB
- `web/app/static/js/anticipos_detalle.js` — 23 líneas, 0.6 KB
- `web/app/static/js/anticipos_edig.js` — 52 líneas, 1.6 KB
- `web/app/static/js/certificados_nuevo.js` — 109 líneas, 3.3 KB
- `web/app/static/js/contratos_form.js` — 65 líneas, 1.7 KB
- `web/app/static/js/contratos_generar.js` — 23 líneas, 0.6 KB
- `web/app/static/js/contratos_listado.js` — 118 líneas, 3.5 KB
- `web/app/static/js/contratos_vencimientos_listado.js` — 385 líneas, 11.9 KB
- `web/app/static/js/dashboard_personal_mes.js` — 151 líneas, 4.5 KB
- `web/app/static/js/dashboard_solicitudes_fondos.js` — 80 líneas, 2.7 KB
- `web/app/static/js/desvinculaciones_carta_aviso.js` — 46 líneas, 1.4 KB
- `web/app/static/js/desvinculaciones_finiquito_generar.js` — 323 líneas, 14.2 KB
- `web/app/static/js/desvinculaciones_listado.js` — 19 líneas, 0.5 KB
- `web/app/static/js/documentos_contrato.js` — 62 líneas, 2.0 KB
- `web/app/static/js/egresos_form.js` — 216 líneas, 6.8 KB
- `web/app/static/js/extras_remuneracion_lote_detalle.js` — 106 líneas, 3.2 KB
- `web/app/static/js/extras_remuneracion_lote_nuevo.js` — 43 líneas, 1.3 KB
- `web/app/static/js/horarios_form.js` — 63 líneas, 2.0 KB
- `web/app/static/js/horas_extras_pacto_form.js` — 398 líneas, 12.6 KB
- `web/app/static/js/horas_extras_revision_remu.js` — 88 líneas, 3.0 KB
- `web/app/static/js/inasistencias_form.js` — 223 líneas, 6.1 KB
- `web/app/static/js/inasistencias_revision.js` — 98 líneas, 3.3 KB
- `web/app/static/js/main.js` — 344 líneas, 12.0 KB
- `web/app/static/js/obras_form.js` — 22 líneas, 0.7 KB
- `web/app/static/js/pago_proveedores_listado.js` — 4 líneas, 0.2 KB
- `web/app/static/js/prevencion_contratos_selector.js` — 155 líneas, 6.3 KB
- `web/app/static/js/prevencion_epp_form.js` — 39 líneas, 1.1 KB
- `web/app/static/js/rendiciones_detalle.js` — 33 líneas, 1.8 KB
- `web/app/static/js/rendiciones_nueva.js` — 27 líneas, 0.8 KB
- `web/app/static/js/solicitudes_fondos_detalle.js` — 47 líneas, 1.2 KB
- `web/app/static/js/trabajadores_form.js` — 113 líneas, 3.6 KB
- `web/app/static/js/transferencias_bancarias_crear.js` — 276 líneas, 7.3 KB
- `web/app/static/js/vacaciones_form.js` — 126 líneas, 3.2 KB

## 6. Uso de estilos y scripts inline en templates

| Template | `style=` | `<script>` |
|---|---:|---:|
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_imprimir_pdf.html` | 35 | 0 |
| `web/app/templates/dashboard/personal_mes.html` | 5 | 6 |
| `web/app/templates/contratos/contrato_detalle.html` | 22 | 0 |
| `web/app/templates/desvinculaciones/desvinculaciones_listado.html` | 18 | 1 |
| `web/app/templates/solicitudes_fondos/detalle.html` | 12 | 2 |
| `web/app/templates/contratos_vencimientos/listado.html` | 11 | 1 |
| `web/app/templates/prevencion_riesgos/epp_form.html` | 7 | 2 |
| `web/app/templates/dashboard/solicitudes_fondos.html` | 3 | 3 |
| `web/app/templates/horarios/horario_form.html` | 5 | 2 |
| `web/app/templates/anticipos/anticipos_imprimir.html` | 11 | 0 |
| `web/app/templates/extras_remuneracion/lote_detalle.html` | 4 | 2 |
| `web/app/templates/solicitudes_fondos/listado.html` | 10 | 0 |
| `web/app/templates/transferencias_bancarias/crear.html` | 7 | 1 |
| `web/app/templates/rendiciones_gastos/detalle.html` | 6 | 1 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_nominas_banco_historico.html` | 9 | 0 |
| `web/app/templates/rendiciones_gastos/rendiciones_gastos_imprimir_pdf.html` | 8 | 0 |
| `web/app/templates/inasistencias/nuevo.html` | 5 | 1 |
| `web/app/templates/inasistencias/editar.html` | 5 | 1 |
| `web/app/templates/rendiciones_gastos/listado.html` | 7 | 0 |
| `web/app/templates/sueldos/sueldos_detalle.html` | 7 | 0 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_nominas_banco_preparar.html` | 7 | 0 |
| `web/app/templates/anticipos/anticipos_detalle.html` | 4 | 1 |
| `web/app/templates/vacaciones/form.html` | 1 | 2 |
| `web/app/templates/horas_extras/pacto_form.html` | 4 | 1 |
| `web/app/templates/horas_extras/pactos_listado.html` | 7 | 0 |
| `web/app/templates/base.html` | 0 | 2 |
| `web/app/templates/anexos_masivos/detalle.html` | 3 | 1 |
| `web/app/templates/trabajadores/nuevo_trabajador.html` | 3 | 1 |
| `web/app/templates/trabajadores/trabajador_detalle.html` | 6 | 0 |
| `web/app/templates/inasistencias/revision.html` | 2 | 1 |

## 7. Plantillas DOCX detectadas

- `web/app/document_templates/anexos/anexo_42_hrs.docx` — 83.9 KB
- `web/app/document_templates/anexos/anexo_cambio_cargo.docx` — 56.9 KB
- `web/app/document_templates/anexos/anexo_cambio_sueldo.docx` — 56.8 KB
- `web/app/document_templates/anexos/anexo_extension_contrato.docx` — 415.0 KB
- `web/app/document_templates/anexos/anexo_indefinido_contrato.docx` — 414.9 KB
- `web/app/document_templates/anexos/anexo_reemplazo_dia.docx` — 57.3 KB
- `web/app/document_templates/anexos/anexo_sueldo_minimo.docx` — 82.2 KB
- `web/app/document_templates/certificados/certif_antiguedad.docx` — 345.8 KB
- `web/app/document_templates/contratos/cargos.docx` — 46.8 KB
- `web/app/document_templates/contratos/contrato_base.docx` — 424.2 KB
- `web/app/document_templates/desvinculacion/1.docx` — 3102.4 KB
- `web/app/document_templates/desvinculacion/4.docx` — 54.3 KB
- `web/app/document_templates/desvinculacion/7.docx` — 56.8 KB
- `web/app/document_templates/desvinculacion/8.docx` — 56.2 KB
- `web/app/document_templates/desvinculacion/finiquito.docx` — 391.8 KB
- `web/app/document_templates/extras/anexo_bono.docx` — 415.3 KB
- `web/app/document_templates/extras/anexo_horas_extra.docx` — 415.3 KB
- `web/app/document_templates/extras/anexo_sabado.docx` — 415.3 KB
- `web/app/document_templates/extras/anexo_trato.docx` — 415.7 KB
- `web/app/document_templates/extras/pacto_hr_ex.docx` — 404.6 KB
- `web/app/document_templates/solicitudes/acuerdo_de_pago.docx` — 68.4 KB
- `web/app/document_templates/solicitudes/egreso.docx` — 53.2 KB
- `web/app/document_templates/solicitudes/vacaciones.docx` — 58.2 KB

## 8. Archivos sospechosos o candidatos a revisión

- `web/app/models_legacy.py` — 86.7 KB

## 9. Notas Fase 1

- Se agregó `web/app/common/navigation.py` para validar redirecciones internas (`next` / `next_url`).
- Se agregó `web/app/services/documentos_laborales.py` como base del expediente documental unificado.
- La generación de contratos registra automáticamente DOCX/PDF en `documentos_laborales`.
- El detalle del contrato ahora muestra checklist documental y últimos documentos registrados.
