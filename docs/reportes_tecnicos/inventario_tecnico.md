# Sistema Grupo CS - Inventario Técnico

Reporte generado automáticamente desde `/srv/rrhh_app`.

## 1. Resumen general

- Archivos Python: 134
- Templates HTML/Jinja: 137
- Archivos CSS: 1
- Archivos JS: 0
- Plantillas DOCX: 22
- Documentos Markdown: 6

## 2. Blueprints detectados

- `acuerdos_pago` — Python: 2, templates asociados: 3
- `admin` — Python: 2, templates asociados: 2
- `anexos` — Python: 2, templates asociados: 5
- `anexos_cambio_cargo` — Python: 2, templates asociados: 4
- `anexos_cambio_sueldo` — Python: 2, templates asociados: 4
- `anexos_indefinidos` — Python: 2, templates asociados: 6
- `anexos_masivos` — Python: 2, templates asociados: 4
- `anticipos` — Python: 2, templates asociados: 8
- `certificados` — Python: 3, templates asociados: 4
- `contratos` — Python: 2, templates asociados: 5
- `contratos_vencimientos` — Python: 2, templates asociados: 1
- `core` — Python: 2, templates asociados: 0
- `dashboard` — Python: 2, templates asociados: 3
- `desvinculaciones` — Python: 2, templates asociados: 6
- `documentos` — Python: 2, templates asociados: 3
- `egresos` — Python: 2, templates asociados: 3
- `extras_remuneracion` — Python: 2, templates asociados: 3
- `feriados` — Python: 2, templates asociados: 2
- `horarios` — Python: 2, templates asociados: 2
- `horas_extras` — Python: 2, templates asociados: 8
- `inasistencias` — Python: 2, templates asociados: 4
- `obras` — Python: 2, templates asociados: 3
- `pago_proveedores` — Python: 2, templates asociados: 6
- `parametros_laborales` — Python: 2, templates asociados: 3
- `rendiciones_gastos` — Python: 2, templates asociados: 6
- `solicitudes_fondos` — Python: 2, templates asociados: 9
- `sueldos` — Python: 1, templates asociados: 5
- `terceros` — Python: 2, templates asociados: 5
- `trabajadores` — Python: 3, templates asociados: 4
- `transferencias_bancarias` — Python: 2, templates asociados: 2
- `vacaciones` — Python: 2, templates asociados: 4

## 3. Archivos Python más grandes

| Archivo | Líneas | KB |
|---|---:|---:|
| `web/app/blueprints/solicitudes_fondos/routes.py` | 2642 | 95.3 |
| `web/app/models_legacy.py` | 2294 | 85.6 |
| `web/app/blueprints/anticipos/routes.py` | 2182 | 73.0 |
| `web/app/blueprints/desvinculaciones/routes.py` | 2037 | 68.2 |
| `web/app/blueprints/rendiciones_gastos/routes.py` | 1522 | 47.2 |
| `web/app/blueprints/horas_extras/routes.py` | 1520 | 52.5 |
| `web/app/blueprints/vacaciones/routes.py` | 1170 | 38.4 |
| `web/app/blueprints/dashboard/routes.py` | 1156 | 38.3 |
| `web/app/blueprints/sueldos/routes.py` | 1132 | 37.6 |
| `web/app/blueprints/trabajadores/routes.py` | 1068 | 38.7 |
| `web/app/blueprints/contratos/routes.py` | 930 | 34.9 |
| `web/app/blueprints/extras_remuneracion/routes.py` | 873 | 28.5 |
| `web/app/cli.py` | 866 | 33.2 |
| `web/app/services/anexos_masivos.py` | 841 | 28.5 |
| `web/app/services/bank_nominas.py` | 836 | 32.1 |
| `web/app/blueprints/inasistencias/routes.py` | 791 | 25.3 |
| `web/app/services/desvinculaciones_docs.py` | 761 | 25.9 |
| `web/app/services/docx_engine.py` | 727 | 22.1 |
| `web/app/blueprints/anexos_indefinidos/routes.py` | 671 | 22.9 |
| `web/app/blueprints/acuerdos_pago/routes.py` | 638 | 20.5 |
| `web/app/blueprints/pago_proveedores/routes.py` | 617 | 20.4 |
| `web/app/blueprints/certificados/routes.py` | 569 | 17.6 |
| `web/app/blueprints/anexos/routes.py` | 536 | 18.8 |
| `web/app/services/acuerdos_pago_docs.py` | 531 | 17.3 |
| `web/app/blueprints/anexos_cambio_sueldo/routes.py` | 525 | 19.2 |
| `web/app/services/solicitudes_fondos_nominas_banco.py` | 501 | 16.9 |
| `web/app/blueprints/anexos_cambio_cargo/routes.py` | 498 | 18.0 |
| `web/app/blueprints/contratos_vencimientos/routes.py` | 466 | 15.2 |
| `web/app/blueprints/egresos/routes.py` | 443 | 14.2 |
| `web/app/services/finiquitos_calc.py` | 443 | 13.8 |

## 4. Templates HTML/Jinja más grandes

| Template | Líneas | KB |
|---|---:|---:|
| `web/app/templates/trabajadores/trabajador_detalle.html` | 900 | 39.4 |
| `web/app/templates/solicitudes_fondos/detalle.html` | 868 | 42.5 |
| `web/app/templates/contratos_vencimientos/listado.html` | 834 | 32.3 |
| `web/app/templates/desvinculaciones/finiquito_generar.html` | 788 | 34.7 |
| `web/app/templates/horas_extras/pacto_form.html` | 698 | 23.6 |
| `web/app/templates/dashboard/solicitudes_fondos.html` | 672 | 24.0 |
| `web/app/templates/trabajadores/nuevo_trabajador.html` | 663 | 31.1 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_imprimir_pdf.html` | 662 | 20.4 |
| `web/app/templates/trabajadores/trabajador_editar.html` | 617 | 30.1 |
| `web/app/templates/anticipos/anticipos_detalle.html` | 558 | 21.5 |
| `web/app/templates/dashboard/personal_mes.html` | 539 | 19.6 |
| `web/app/templates/rendiciones_gastos/detalle.html` | 526 | 22.7 |
| `web/app/templates/extras_remuneracion/lote_detalle.html` | 485 | 22.1 |
| `web/app/templates/anexos_masivos/detalle.html` | 472 | 17.5 |
| `web/app/templates/inasistencias/revision.html` | 438 | 18.7 |
| `web/app/templates/horas_extras/revision_remu.html` | 425 | 18.9 |
| `web/app/templates/egresos/egreso_form.html` | 424 | 15.0 |
| `web/app/templates/contratos/contratos.html` | 419 | 17.3 |
| `web/app/templates/base.html` | 415 | 23.2 |
| `web/app/templates/transferencias_bancarias/crear.html` | 401 | 11.8 |
| `web/app/templates/contratos/contrato_generar.html` | 381 | 13.1 |
| `web/app/templates/desvinculaciones/desvinculaciones_listado.html` | 378 | 15.2 |
| `web/app/templates/contratos/contrato_editar.html` | 370 | 15.3 |
| `web/app/templates/sueldos/sueldos_detalle.html` | 368 | 15.5 |
| `web/app/templates/acuerdos_pago/acuerdos_pago_form.html` | 365 | 12.9 |
| `web/app/templates/desvinculaciones/carta_aviso_generar.html` | 337 | 15.2 |
| `web/app/templates/dashboard/bienestar.html` | 333 | 12.3 |
| `web/app/templates/parametros_laborales/form.html` | 327 | 11.9 |
| `web/app/templates/contratos/nuevo_contrato.html` | 318 | 13.3 |
| `web/app/templates/anticipos/anticipos_imprimir_pdf.html` | 291 | 7.5 |

## 5. Archivos estáticos

### CSS

- `web/app/static/styles.css` — 1007 líneas, 19.7 KB

### JS

- No se detectaron archivos JS propios.

## 6. Uso de estilos y scripts inline en templates

| Template | `style=` | `<script>` |
|---|---:|---:|
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_imprimir_pdf.html` | 35 | 0 |
| `web/app/templates/contratos/contrato_detalle.html` | 20 | 0 |
| `web/app/templates/desvinculaciones/desvinculaciones_listado.html` | 18 | 1 |
| `web/app/templates/solicitudes_fondos/detalle.html` | 12 | 2 |
| `web/app/templates/contratos_vencimientos/listado.html` | 11 | 1 |
| `web/app/templates/anticipos/anticipos_imprimir.html` | 11 | 0 |
| `web/app/templates/solicitudes_fondos/listado.html` | 10 | 0 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_nominas_banco_historico.html` | 9 | 0 |
| `web/app/templates/rendiciones_gastos/rendiciones_gastos_imprimir_pdf.html` | 8 | 0 |
| `web/app/templates/transferencias_bancarias/crear.html` | 7 | 1 |
| `web/app/templates/dashboard/personal_mes.html` | 5 | 2 |
| `web/app/templates/dashboard/solicitudes_fondos.html` | 3 | 4 |
| `web/app/templates/horas_extras/pactos_listado.html` | 7 | 0 |
| `web/app/templates/rendiciones_gastos/detalle.html` | 6 | 1 |
| `web/app/templates/rendiciones_gastos/listado.html` | 7 | 0 |
| `web/app/templates/solicitudes_fondos/solicitudes_fondos_nominas_banco_preparar.html` | 7 | 0 |
| `web/app/templates/sueldos/sueldos_detalle.html` | 7 | 0 |
| `web/app/templates/trabajadores/nuevo_trabajador.html` | 3 | 4 |
| `web/app/templates/extras_remuneracion/lote_detalle.html` | 4 | 2 |
| `web/app/templates/horarios/horario_form.html` | 5 | 1 |
| `web/app/templates/horas_extras/pacto_form.html` | 4 | 2 |
| `web/app/templates/inasistencias/editar.html` | 5 | 1 |
| `web/app/templates/inasistencias/nuevo.html` | 5 | 1 |
| `web/app/templates/trabajadores/trabajador_detalle.html` | 6 | 0 |
| `web/app/templates/acuerdos_pago/acuerdos_pago_listado.html` | 5 | 0 |
| `web/app/templates/anticipos/anticipos_detalle.html` | 4 | 1 |
| `web/app/templates/certificados/listado.html` | 5 | 0 |
| `web/app/templates/feriados/listado.html` | 5 | 0 |
| `web/app/templates/anexos_masivos/detalle.html` | 3 | 1 |
| `web/app/templates/contratos/contrato_generar.html` | 2 | 2 |
| `web/app/templates/contratos/nuevo_contrato.html` | 2 | 2 |
| `web/app/templates/egresos/egresos_listado.html` | 4 | 0 |
| `web/app/templates/trabajadores/trabajador_editar.html` | 2 | 2 |
| `web/app/templates/cargos/cargos_listado.html` | 3 | 0 |
| `web/app/templates/contratos/contrato_editar.html` | 1 | 2 |
| `web/app/templates/egresos/egreso_form.html` | 2 | 1 |
| `web/app/templates/vacaciones/form.html` | 1 | 2 |
| `web/app/templates/acuerdos_pago/acuerdos_pago_form.html` | 1 | 1 |
| `web/app/templates/admin/user_form.html` | 2 | 0 |
| `web/app/templates/anexos_cambio_cargo/nuevo.html` | 1 | 1 |

## 7. Plantillas DOCX detectadas

- `web/app/document_templates/anexos/anexo_42_hrs.docx` — 83.9 KB
- `web/app/document_templates/anexos/anexo_cambio_cargo.docx` — 56.9 KB
- `web/app/document_templates/anexos/anexo_cambio_sueldo.docx` — 56.8 KB
- `web/app/document_templates/anexos/anexo_extension_contrato.docx` — 415.0 KB
- `web/app/document_templates/anexos/anexo_indefinido_contrato.docx` — 414.9 KB
- `web/app/document_templates/anexos/anexo_sueldo_minimo.docx` — 82.2 KB
- `web/app/document_templates/certificados/certif_antiguedad.docx` — 345.8 KB
- `web/app/document_templates/contratos/cargos.docx` — 43.8 KB
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

- `web/app/blueprints/certificados/services (eliminar).py` — 5.7 KB
- `web/app/models_legacy.py` — 85.6 KB
- `web/migrations/versions/3823802a0074_add_requiere_carta_y_carta_template_a_.py` — 1.8 KB

## 9. Funciones helper repetidas o candidatas a centralización

| Función | Apariciones | Archivos |
|---|---:|---|
| `_parse_date` | 8 | `web/app/blueprints/anexos_indefinidos/routes.py`<br>`web/app/blueprints/contratos_vencimientos/routes.py`<br>`web/app/blueprints/feriados/routes.py`<br>`web/app/blueprints/obras/routes.py`<br>`web/app/blueprints/parametros_laborales/routes.py`<br>`web/app/blueprints/vacaciones/routes.py`<br>`web/app/cli.py`<br>`web/app/import_contratos_quintero.py` |
| `_to_decimal` | 6 | `web/app/blueprints/acuerdos_pago/routes.py`<br>`web/app/blueprints/egresos/routes.py`<br>`web/app/blueprints/extras_remuneracion/routes.py`<br>`web/app/services/bank_nominas.py`<br>`web/app/services/finiquitos_calc.py`<br>`web/app/services/solicitudes_fondos_nominas_banco.py` |
| `_to_int` | 5 | `web/app/blueprints/acuerdos_pago/routes.py`<br>`web/app/blueprints/anticipos/routes.py`<br>`web/app/blueprints/egresos/routes.py`<br>`web/app/blueprints/extras_remuneracion/routes.py`<br>`web/app/blueprints/sueldos/routes.py` |
| `_fmt_clp` | 5 | `web/app/blueprints/anexos_cambio_sueldo/routes.py`<br>`web/app/blueprints/desvinculaciones/routes.py`<br>`web/app/services/acuerdos_pago_docs.py`<br>`web/app/services/egresos_docs.py`<br>`web/app/services/extras_docs.py` |
| `_fmt_fecha_es` | 5 | `web/app/blueprints/certificados/services (eliminar).py`<br>`web/app/services/acuerdos_pago_docs.py`<br>`web/app/services/certificados_docs.py`<br>`web/app/services/egresos_docs.py`<br>`web/app/services/pactos_hr_extras_docs.py` |
| `format_rut` | 4 | `web/app/blueprints/anticipos/routes.py`<br>`web/app/blueprints/contratos/routes.py`<br>`web/app/blueprints/sueldos/routes.py`<br>`web/app/blueprints/trabajadores/routes.py` |
| `_split_rut` | 3 | `web/app/blueprints/desvinculaciones/routes.py`<br>`web/app/blueprints/trabajadores/api.py`<br>`web/app/services/solicitudes_fondos_nominas_banco.py` |
| `_format_rut` | 3 | `web/app/blueprints/horas_extras/routes.py`<br>`web/app/blueprints/inasistencias/routes.py`<br>`web/app/services/desvinculaciones_docs.py` |
| `_to_date` | 2 | `web/app/blueprints/acuerdos_pago/routes.py`<br>`web/app/blueprints/egresos/routes.py` |
| `_format_rut_documento` | 2 | `web/app/blueprints/anexos_cambio_cargo/routes.py`<br>`web/app/blueprints/anexos_cambio_sueldo/routes.py` |
| `_parse_money` | 2 | `web/app/blueprints/anexos_cambio_sueldo/routes.py`<br>`web/app/services/import_anticipos.py` |
| `_rut_sin_puntos_con_guion` | 2 | `web/app/blueprints/anticipos/routes.py`<br>`web/app/services/import_sueldos.py` |
| `_money_to_int` | 2 | `web/app/blueprints/desvinculaciones/routes.py`<br>`web/app/services/desvinculaciones_docs.py` |
| `_clp_int` | 2 | `web/app/blueprints/extras_remuneracion/routes.py`<br>`web/app/services/extras_csv.py` |
| `_parse_date_yyyy_mm_dd` | 2 | `web/app/blueprints/horas_extras/routes.py`<br>`web/app/blueprints/pago_proveedores/routes.py` |
| `_fmt_rut_from_user` | 2 | `web/app/blueprints/solicitudes_fondos/routes.py`<br>`web/app/blueprints/solicitudes_fondos/routes.py` |
| `split_rut` | 2 | `web/app/blueprints/trabajadores/routes.py`<br>`web/app/services/import_anticipos.py` |
| `parse_date` | 2 | `web/app/import_trabajadores_quintero.py`<br>`web/app/utils.py` |
| `rut_completo` | 2 | `web/app/models_legacy.py`<br>`web/app/models_legacy.py` |
| `_fmt_rut_cl` | 2 | `web/app/services/acuerdos_pago_docs.py`<br>`web/app/services/egresos_docs.py` |
| `rut_trabajador_filter` | 1 | `web/app/__init__.py` |
| `rut_any_filter` | 1 | `web/app/__init__.py` |
| `rut_tercero_filter` | 1 | `web/app/__init__.py` |
| `_to_clp_int` | 1 | `web/app/blueprints/acuerdos_pago/routes.py` |
| `_normalize_rut` | 1 | `web/app/blueprints/admin/routes.py` |
| `_clp_palabras_sin_pesos` | 1 | `web/app/blueprints/anexos_cambio_sueldo/routes.py` |
| `_get_fecha_termino_referencial_y_sugerencia_desde` | 1 | `web/app/blueprints/anexos_indefinidos/routes.py` |
| `_rut_con_puntos` | 1 | `web/app/blueprints/anticipos/routes.py` |
| `_format_rut_show` | 1 | `web/app/blueprints/anticipos/routes.py` |
| `_rut_trabajador_para_edig` | 1 | `web/app/blueprints/anticipos/routes.py` |
| `_rut_digits` | 1 | `web/app/blueprints/certificados/routes.py` |
| `_resolver_ruta_destino_nextcloud` | 1 | `web/app/blueprints/certificados/services (eliminar).py` |
| `split_empleador_rut` | 1 | `web/app/blueprints/contratos/routes.py` |
| `format_rut_raw` | 1 | `web/app/blueprints/contratos/routes.py` |
| `_rut_completo_expr` | 1 | `web/app/blueprints/dashboard/routes.py` |
| `_fecha_ingreso_efectiva_expr` | 1 | `web/app/blueprints/dashboard/routes.py` |
| `_next_anniversary_date_expr` | 1 | `web/app/blueprints/dashboard/routes.py` |
| `_parse_money_to_str` | 1 | `web/app/blueprints/desvinculaciones/routes.py` |
| `_money_to_int_any` | 1 | `web/app/blueprints/desvinculaciones/routes.py` |
| `_fmt_fecha_pago` | 1 | `web/app/blueprints/desvinculaciones/routes.py` |
| `_fmt_fecha_ddmmyyyy` | 1 | `web/app/blueprints/desvinculaciones/routes.py` |
| `_parse_fecha_pago_any` | 1 | `web/app/blueprints/desvinculaciones/routes.py` |
| `_clp_sin_decimales` | 1 | `web/app/blueprints/extras_remuneracion/routes.py` |
| `_fecha_termino_max_pacto` | 1 | `web/app/blueprints/horas_extras/routes.py` |
| `_to_decimal_money` | 1 | `web/app/blueprints/solicitudes_fondos/routes.py` |
| `_fmt_clp_text` | 1 | `web/app/blueprints/solicitudes_fondos/routes.py` |
| `_rut_plain_from_user` | 1 | `web/app/blueprints/solicitudes_fondos/routes.py` |
| `_split_rut_plain` | 1 | `web/app/blueprints/solicitudes_fondos/routes.py` |
| `_parse_rut_parts_from_excel` | 1 | `web/app/blueprints/terceros/routes.py` |
| `_parse_rut_cta` | 1 | `web/app/blueprints/terceros/routes.py` |
| `trabajador_rut_formateado` | 1 | `web/app/blueprints/trabajadores/routes.py` |
| `normalizar_y_guardar_rut_en_trabajador` | 1 | `web/app/blueprints/trabajadores/routes.py` |
| `_fmt_fecha` | 1 | `web/app/blueprints/trabajadores/routes.py` |
| `_bank_sanitize_text` | 1 | `web/app/blueprints/transferencias_bancarias/routes.py` |
| `_format_rut_con_puntos` | 1 | `web/app/blueprints/vacaciones/routes.py` |
| `_clean_rut_digits` | 1 | `web/app/cli.py` |
| `_parse_rut_completo` | 1 | `web/app/cli.py` |
| `normalizar_nombre_trabajador` | 1 | `web/app/config.py` |
| `_normalizar_texto_simple` | 1 | `web/app/config.py` |
| `rut_cta_completo` | 1 | `web/app/models_legacy.py` |
| `ruta_nextcloud` | 1 | `web/app/models_legacy.py` |
| `ruta_nextcloud_preferente` | 1 | `web/app/models_legacy.py` |
| `ruta_completa` | 1 | `web/app/models_legacy.py` |
| `ruta_docx_completa` | 1 | `web/app/models_legacy.py` |
| `ruta_pdf_completa` | 1 | `web/app/models_legacy.py` |
| `_formato_clp_sin_decimales` | 1 | `web/app/services/anexos_masivos.py` |
| `obtener_parametro_vigente_para_fecha` | 1 | `web/app/services/anexos_masivos.py` |
| `rut_plain_from_parts` | 1 | `web/app/services/bank_nominas.py` |
| `rut_plain_from_str` | 1 | `web/app/services/bank_nominas.py` |
| `_split_rut_dv` | 1 | `web/app/services/certificados_docs.py` |
| `_format_rut_with_dots` | 1 | `web/app/services/certificados_docs.py` |
| `fecha_larga_el` | 1 | `web/app/services/date_format.py` |
| `_fmt_clp_blank_if_zero` | 1 | `web/app/services/egresos_docs.py` |
| `_fmt_fecha_corta` | 1 | `web/app/services/extras_docs.py` |
| `_money` | 1 | `web/app/services/finiquitos_calc.py` |
| `fecha_base_feriado_proporcional` | 1 | `web/app/services/finiquitos_calc.py` |
| `_clean_rut_compact` | 1 | `web/app/services/import_anticipos.py` |
| `_is_valid_rut` | 1 | `web/app/services/import_sueldos.py` |
| `clp_a_palabras` | 1 | `web/app/services/num_to_words_es.py` |
| `rut_parts_from_plain` | 1 | `web/app/services/pago_proveedores_engine.py` |
| `periodo_from_date` | 1 | `web/app/services/parametros_laborales.py` |
| `normalizar_periodo` | 1 | `web/app/services/parametros_laborales.py` |
| `obtener_parametro_por_fecha` | 1 | `web/app/services/parametros_laborales.py` |
| `_money_to_decimal_str` | 1 | `web/app/services/previred_import.py` |
| `rut_con_puntos` | 1 | `web/app/services/rut_format.py` |
| `_rut_plain` | 1 | `web/app/services/solicitudes_fondos_nominas_banco.py` |
| `collect_nomina_candidates` | 1 | `web/app/services/solicitudes_fondos_nominas_banco.py` |
| `create_nomina_from_candidates` | 1 | `web/app/services/solicitudes_fondos_nominas_banco.py` |
| `format_rut_parts` | 1 | `web/app/utils.py` |
| `fecha_larga_es` | 1 | `web/app/utils.py` |
| `format_rut_with_dots` | 1 | `web/app/utils.py` |

## 10. Referencias a `models_legacy`

- `web/app/models/__init__.py`
- `web/app/models_legacy.py`

## 11. Búsqueda de posibles secuencias de escape problemáticas

- `web/app/blueprints/anexos/routes.py`
- `web/app/blueprints/anexos_cambio_cargo/routes.py`
- `web/app/blueprints/anexos_cambio_sueldo/routes.py`
- `web/app/blueprints/anexos_indefinidos/routes.py`
- `web/app/blueprints/anticipos/routes.py`
- `web/app/blueprints/contratos/routes.py`
- `web/app/blueprints/rendiciones_gastos/routes.py`
- `web/app/services/anexos_masivos.py`
- `web/app/services/extras_csv.py`
- `web/app/services/extras_docs.py`
