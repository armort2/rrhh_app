"""
Servicios de lectura para Expediente Laboral 360.

Este módulo concentra cálculos de salud/estado para pantallas de consulta.
No modifica base de datos y puede reutilizarse en ficha trabajador, contrato,
reportería y futuros tableros de cumplimiento.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..models import ParametroLaboral


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def fmt_clp(value: Any) -> str:
    val = _as_decimal(value)
    if val is None:
        val = Decimal("0")
    return "$" + f"{int(round(float(val))):,}".replace(",", ".")


def _score_label(score: int) -> tuple[str, str]:
    if score >= 90:
        return "Excelente", "success"
    if score >= 75:
        return "Controlado", "primary"
    if score >= 55:
        return "Revisar", "warning"
    return "Crítico", "danger"


def _format_antiguedad(fecha_inicio: date | None, fecha_corte: date | None = None) -> str:
    if not fecha_inicio:
        return "Sin inicio"

    fecha_corte = fecha_corte or date.today()
    if fecha_corte < fecha_inicio:
        return "Aún no inicia"

    total_dias = (fecha_corte - fecha_inicio).days + 1
    anios = total_dias // 365
    meses = (total_dias % 365) // 30
    dias = (total_dias % 365) % 30

    partes: list[str] = []
    if anios:
        partes.append(f"{anios} año{'s' if anios != 1 else ''}")
    if meses:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if not partes:
        partes.append(f"{dias} día{'s' if dias != 1 else ''}")
    return " · ".join(partes)


def obtener_parametro_laboral_vigente(fecha_ref: date | None = None) -> ParametroLaboral | None:
    """Obtiene el parámetro laboral vigente o, como fallback, el último cargado."""
    fecha_ref = fecha_ref or date.today()

    vigente = (
        ParametroLaboral.query
        .filter(ParametroLaboral.fecha_vigencia_desde <= fecha_ref)
        .filter(ParametroLaboral.fecha_vigencia_hasta >= fecha_ref)
        .order_by(ParametroLaboral.fecha_vigencia_desde.desc(), ParametroLaboral.id.desc())
        .first()
    )
    if vigente:
        return vigente

    return (
        ParametroLaboral.query
        .filter(ParametroLaboral.fecha_vigencia_desde <= fecha_ref)
        .order_by(ParametroLaboral.fecha_vigencia_desde.desc(), ParametroLaboral.id.desc())
        .first()
    )


def build_contrato_360(
    contrato: Any,
    *,
    documento_checklist: dict[str, Any] | None = None,
    documentos_registrados: list[Any] | None = None,
    fecha_ref: date | None = None,
) -> dict[str, Any]:
    """Construye un resumen ejecutivo y operativo de un contrato."""
    hoy = fecha_ref or date.today()
    documentos_registrados = documentos_registrados or []
    documento_checklist = documento_checklist or {}

    fecha_inicio = getattr(contrato, "fecha_inicio", None)
    fecha_termino = getattr(contrato, "fecha_termino", None)
    estado = (getattr(contrato, "estado_contrato", None) or "").upper()

    dias_transcurridos = (hoy - fecha_inicio).days + 1 if fecha_inicio and hoy >= fecha_inicio else None
    dias_restantes = (fecha_termino - hoy).days if fecha_termino else None

    if estado == "VIGENTE" and dias_restantes is not None and dias_restantes < 0:
        estado_operativo = "Vigente vencido"
        estado_clase = "danger"
        estado_detalle = "El contrato figura vigente, pero su fecha de término ya pasó."
    elif estado == "VIGENTE" and dias_restantes is not None and dias_restantes <= 15:
        estado_operativo = "Vence en breve"
        estado_clase = "warning"
        estado_detalle = f"Quedan {dias_restantes} día(s) para el término pactado."
    elif estado == "VIGENTE" and dias_restantes is not None and dias_restantes <= 45:
        estado_operativo = "Próximo a vencer"
        estado_clase = "warning"
        estado_detalle = f"Quedan {dias_restantes} día(s); conviene definir continuidad o salida."
    elif estado == "VIGENTE":
        estado_operativo = "Vigente controlado"
        estado_clase = "success"
        estado_detalle = "Sin alertas críticas de vigencia por fecha."
    elif estado:
        estado_operativo = estado.title()
        estado_clase = "secondary"
        estado_detalle = "Contrato no marcado como vigente."
    else:
        estado_operativo = "Sin estado"
        estado_clase = "danger"
        estado_detalle = "Falta estado contractual."

    parametro = obtener_parametro_laboral_vigente(hoy)
    sueldo_minimo = _as_decimal(getattr(parametro, "renta_minima_dependiente", None)) if parametro else None
    sueldo_base = _as_decimal(getattr(contrato, "sueldo_base", None))

    alertas: list[dict[str, str]] = []

    if not fecha_inicio:
        alertas.append({
            "nivel": "danger",
            "icono": "📅",
            "titulo": "Falta fecha de inicio",
            "detalle": "La fecha de inicio es obligatoria para documentos, feriados, antigüedad y finiquito.",
        })

    if estado == "VIGENTE" and dias_restantes is not None and dias_restantes < 0:
        alertas.append({
            "nivel": "danger",
            "icono": "⏰",
            "titulo": "Contrato vencido marcado como vigente",
            "detalle": "Revisar si corresponde anexo, paso a indefinido, término o corrección de estado.",
        })
    elif estado == "VIGENTE" and dias_restantes is not None and dias_restantes <= 45:
        alertas.append({
            "nivel": "warning",
            "icono": "⏳",
            "titulo": "Contrato próximo a vencer",
            "detalle": "Conviene definir continuidad, carta de aviso o regularización antes del vencimiento.",
        })

    horas = getattr(contrato, "horas_semanales", None)
    try:
        horas_num = int(horas) if horas is not None else None
    except (TypeError, ValueError):
        horas_num = None
    if horas_num and horas_num > 42:
        alertas.append({
            "nivel": "warning",
            "icono": "🕒",
            "titulo": "Jornada superior a 42 horas",
            "detalle": "Revisar jornada contractual y anexos asociados a la reducción legal vigente.",
        })

    if sueldo_minimo is not None and sueldo_base is not None and sueldo_base < sueldo_minimo:
        alertas.append({
            "nivel": "danger",
            "icono": "💰",
            "titulo": "Sueldo base bajo mínimo cargado",
            "detalle": f"Sueldo base {fmt_clp(sueldo_base)} vs mínimo parametrizado {fmt_clp(sueldo_minimo)}.",
        })
    elif sueldo_base is None:
        alertas.append({
            "nivel": "warning",
            "icono": "💰",
            "titulo": "Sueldo base no informado",
            "detalle": "Completar remuneración base antes de generar documentos o cálculos laborales.",
        })

    bloqueantes_doc = documento_checklist.get("bloqueantes") or []
    advertencias_doc = documento_checklist.get("advertencias") or []
    if bloqueantes_doc:
        alertas.append({
            "nivel": "danger",
            "icono": "📄",
            "titulo": "Checklist documental con bloqueantes",
            "detalle": f"Hay {len(bloqueantes_doc)} punto(s) crítico(s) antes de generar respaldos.",
        })
    elif advertencias_doc:
        alertas.append({
            "nivel": "warning",
            "icono": "📄",
            "titulo": "Checklist documental con advertencias",
            "detalle": f"Hay {len(advertencias_doc)} advertencia(s) que conviene revisar.",
        })

    if not documentos_registrados:
        alertas.append({
            "nivel": "info",
            "icono": "🗂️",
            "titulo": "Sin documentos registrados",
            "detalle": "Aún no hay respaldos asociados al expediente documental del contrato.",
        })

    score = 100
    for alerta in alertas:
        if alerta["nivel"] == "danger":
            score -= 20
        elif alerta["nivel"] == "warning":
            score -= 10
        else:
            score -= 4
    score = max(score, 0)
    score_label, score_class = _score_label(score)

    acciones: list[dict[str, str]] = []
    if bloqueantes_doc or not fecha_inicio or sueldo_base is None:
        acciones.append({
            "tipo": "editar",
            "icono": "✏️",
            "label": "Completar contrato",
            "detalle": "Corregir datos críticos antes de emitir documentos.",
            "class": "btn-outline-danger",
        })
    elif not documentos_registrados:
        acciones.append({
            "tipo": "generar_contrato",
            "icono": "📄",
            "label": "Generar contrato",
            "detalle": "Crear respaldo DOCX/PDF y registrarlo en expediente.",
            "class": "btn-primary",
        })

    if estado == "VIGENTE" and dias_restantes is not None and dias_restantes <= 45:
        acciones.extend([
            {
                "tipo": "anexo_extension",
                "icono": "🧩",
                "label": "Preparar extensión",
                "detalle": "Prorrogar contrato antes del vencimiento.",
                "class": "btn-outline-primary",
            },
            {
                "tipo": "anexo_indefinido",
                "icono": "📌",
                "label": "Evaluar indefinido",
                "detalle": "Formalizar continuidad si corresponde.",
                "class": "btn-outline-primary",
            },
        ])

    if sueldo_minimo is not None and sueldo_base is not None and sueldo_base < sueldo_minimo:
        acciones.append({
            "tipo": "cambio_sueldo",
            "icono": "💰",
            "label": "Actualizar sueldo",
            "detalle": "Generar anexo de cambio de sueldo.",
            "class": "btn-outline-danger",
        })

    acciones.append({
        "tipo": "ver_ficha",
        "icono": "👤",
        "label": "Ver expediente",
        "detalle": "Volver a la ficha 360 del trabajador.",
        "class": "btn-outline-secondary",
    })

    return {
        "estado_operativo": estado_operativo,
        "estado_clase": estado_clase,
        "estado_detalle": estado_detalle,
        "score": score,
        "score_label": score_label,
        "score_class": score_class,
        "antiguedad": _format_antiguedad(fecha_inicio, hoy),
        "dias_transcurridos": dias_transcurridos,
        "dias_restantes": dias_restantes,
        "sueldo_minimo": sueldo_minimo,
        "sueldo_minimo_fmt": fmt_clp(sueldo_minimo) if sueldo_minimo is not None else "No cargado",
        "sueldo_base_fmt": fmt_clp(sueldo_base) if sueldo_base is not None else "-",
        "documentos_count": len(documentos_registrados),
        "alertas": alertas[:6],
        "acciones": acciones[:5],
    }


def build_salud_expediente_trabajador(
    *,
    total_contratos: int,
    total_contratos_vigentes: int,
    datos_faltantes: list[str] | None,
    documentos_recientes: list[Any] | None,
    prevencion_resumen: dict[str, Any] | None,
    contratos_por_vencer: list[Any] | None,
) -> dict[str, Any]:
    """Semáforo ejecutivo de la ficha del trabajador."""
    datos_faltantes = datos_faltantes or []
    documentos_recientes = documentos_recientes or []
    prevencion_resumen = prevencion_resumen or {}
    contratos_por_vencer = contratos_por_vencer or []

    checks: list[dict[str, str]] = []

    def add(ok: bool, label: str, ok_detail: str, bad_detail: str, level_bad: str = "warning") -> None:
        checks.append({
            "label": label,
            "estado": "OK" if ok else "REVISAR",
            "detalle": ok_detail if ok else bad_detail,
            "nivel": "success" if ok else level_bad,
        })

    add(
        total_contratos > 0,
        "Contratos asociados",
        f"Registra {total_contratos} contrato(s).",
        "No registra contratos asociados.",
        "danger",
    )
    add(
        total_contratos_vigentes > 0,
        "Vigencia laboral",
        f"Registra {total_contratos_vigentes} contrato(s) vigente(s).",
        "No registra contrato vigente actualmente.",
        "warning",
    )
    add(
        not datos_faltantes,
        "Datos maestros",
        "Datos personales, bancarios y previsionales controlados.",
        "Faltan: " + ", ".join(datos_faltantes[:6]) + ("..." if len(datos_faltantes) > 6 else "."),
        "warning",
    )
    add(
        bool(documentos_recientes),
        "Documentos recientes",
        f"Hay {len(documentos_recientes)} documento(s) visible(s) en el hub.",
        "No hay documentos recientes visibles para el contrato de contexto.",
        "info",
    )
    add(
        int(prevencion_resumen.get("documentos_vencidos") or 0) == 0,
        "Prevención de riesgos",
        "Sin documentos preventivos vencidos detectados.",
        f"Hay {prevencion_resumen.get('documentos_vencidos')} documento(s) preventivo(s) vencido(s).",
        "danger",
    )
    add(
        not contratos_por_vencer,
        "Vencimientos",
        "Sin contratos próximos a vencer en la ventana de control.",
        f"Hay {len(contratos_por_vencer)} contrato(s) dentro de la ventana de 45 días.",
        "warning",
    )

    score = 100
    for check in checks:
        if check["nivel"] == "danger" and check["estado"] != "OK":
            score -= 18
        elif check["nivel"] == "warning" and check["estado"] != "OK":
            score -= 10
        elif check["nivel"] == "info" and check["estado"] != "OK":
            score -= 5

    score = max(score, 0)
    score_label, score_class = _score_label(score)

    return {
        "score": score,
        "score_label": score_label,
        "score_class": score_class,
        "checks": checks,
    }
