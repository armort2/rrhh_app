# web/app/services/cumplimiento_laboral.py
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import (
    Contrato,
    Obra,
    ParametroLaboral,
    PrevCharlaSeguridad,
    PrevDocumentoPreventivo,
    PrevEntregaEPP,
    PrevEntregaEPPItem,
    Trabajador,
)
from .parametros_laborales import obtener_parametro_vigente, periodo_from_date


VENTANA_ALERTA_DIAS = 30
MAX_LISTA = 8


def _hoy() -> date:
    return date.today()


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _fmt_clp(value: Any) -> str:
    dec = _decimal_or_none(value)
    if dec is None:
        return "-"
    return f"${int(dec):,}".replace(",", ".")


def _fmt_date(value: Any) -> str:
    if not value:
        return "-"
    try:
        return value.strftime("%d-%m-%Y")
    except Exception:
        return str(value)


def _nombre_trabajador(trabajador: Trabajador | None) -> str:
    if not trabajador:
        return "Sin trabajador"
    partes = [
        getattr(trabajador, "ap_paterno", None),
        getattr(trabajador, "ap_materno", None),
        getattr(trabajador, "nombres", None),
    ]
    return " ".join(str(p).strip() for p in partes if p and str(p).strip()) or "Sin nombre"


def _rut_trabajador(trabajador: Trabajador | None) -> str:
    if not trabajador:
        return ""
    rut = (getattr(trabajador, "rut", None) or "").strip()
    dv = (getattr(trabajador, "dv", None) or "").strip().upper()
    return f"{rut}-{dv}" if rut and dv else rut


def _obra_label(obra: Obra | None) -> str:
    if not obra:
        return "Sin obra"
    centro = (getattr(obra, "centro_costo", None) or "").strip()
    return f"{obra.nombre} · {centro}" if centro else obra.nombre


def _contratos_base_query(user):
    q = (
        Contrato.query
        .options(
            joinedload(Contrato.trabajador),
            joinedload(Contrato.obra),
            joinedload(Contrato.empleador),
            joinedload(Contrato.cargo),
        )
    )

    if not getattr(user, "has_role", lambda *_: False)("ADMIN"):
        obra_ids = [o.id for o in (getattr(user, "obras", None) or [])]
        q = q.filter(Contrato.obra_id.in_(obra_ids or [-1]))

    return q


def _contratos_vigentes_query(user):
    return _contratos_base_query(user).filter(Contrato.estado_contrato == "VIGENTE")


def _prev_docs_base_query(user):
    q = (
        PrevDocumentoPreventivo.query
        .options(
            joinedload(PrevDocumentoPreventivo.trabajador),
            joinedload(PrevDocumentoPreventivo.obra),
            joinedload(PrevDocumentoPreventivo.contrato),
        )
    )
    if not getattr(user, "has_role", lambda *_: False)("ADMIN"):
        obra_ids = [o.id for o in (getattr(user, "obras", None) or [])]
        q = q.filter(PrevDocumentoPreventivo.obra_id.in_(obra_ids or [-1]))
    return q


def _epp_items_base_query(user):
    q = (
        PrevEntregaEPPItem.query
        .join(PrevEntregaEPP, PrevEntregaEPP.id == PrevEntregaEPPItem.entrega_id)
        .options(
            joinedload(PrevEntregaEPPItem.tipo_epp),
            joinedload(PrevEntregaEPPItem.entrega).joinedload(PrevEntregaEPP.trabajador),
            joinedload(PrevEntregaEPPItem.entrega).joinedload(PrevEntregaEPP.obra),
        )
    )
    if not getattr(user, "has_role", lambda *_: False)("ADMIN"):
        obra_ids = [o.id for o in (getattr(user, "obras", None) or [])]
        q = q.filter(PrevEntregaEPP.obra_id.in_(obra_ids or [-1]))
    return q


def _charlas_base_query(user):
    q = PrevCharlaSeguridad.query.options(joinedload(PrevCharlaSeguridad.obra))
    if not getattr(user, "has_role", lambda *_: False)("ADMIN"):
        obra_ids = [o.id for o in (getattr(user, "obras", None) or [])]
        q = q.filter(PrevCharlaSeguridad.obra_id.in_(obra_ids or [-1]))
    return q


def _contrato_row(c: Contrato, *, sueldo_minimo: Decimal | None = None) -> dict[str, Any]:
    sueldo = _decimal_or_none(getattr(c, "sueldo_base", None))
    dias_restantes = None
    hoy = _hoy()
    if getattr(c, "fecha_termino", None):
        dias_restantes = (c.fecha_termino - hoy).days

    return {
        "id": c.id,
        "trabajador": _nombre_trabajador(getattr(c, "trabajador", None)),
        "rut": _rut_trabajador(getattr(c, "trabajador", None)),
        "obra": _obra_label(getattr(c, "obra", None)),
        "empleador": getattr(getattr(c, "empleador", None), "razon_social", "Sin empleador"),
        "cargo": getattr(getattr(c, "cargo", None), "nombre", "Sin cargo"),
        "tipo_contrato": getattr(c, "tipo_contrato", None) or "-",
        "fecha_inicio": _fmt_date(getattr(c, "fecha_inicio", None)),
        "fecha_termino": _fmt_date(getattr(c, "fecha_termino", None)),
        "dias_restantes": dias_restantes,
        "horas_semanales": getattr(c, "horas_semanales", None),
        "sueldo_base": _fmt_clp(getattr(c, "sueldo_base", None)),
        "brecha_sueldo": _fmt_clp((sueldo_minimo - sueldo) if sueldo_minimo is not None and sueldo is not None and sueldo < sueldo_minimo else None),
    }


def _doc_row(doc: PrevDocumentoPreventivo) -> dict[str, Any]:
    return {
        "id": doc.id,
        "tipo": getattr(doc, "tipo_documento", None) or "Documento preventivo",
        "trabajador": _nombre_trabajador(getattr(doc, "trabajador", None)),
        "obra": _obra_label(getattr(doc, "obra", None)),
        "estado": getattr(doc, "estado", None) or "-",
        "fecha_emision": _fmt_date(getattr(doc, "fecha_emision", None)),
        "fecha_vencimiento": _fmt_date(getattr(doc, "fecha_vencimiento", None)),
    }


def _epp_row(item: PrevEntregaEPPItem) -> dict[str, Any]:
    entrega = getattr(item, "entrega", None)
    return {
        "entrega_id": getattr(entrega, "id", None),
        "tipo": getattr(getattr(item, "tipo_epp", None), "nombre", "EPP"),
        "trabajador": _nombre_trabajador(getattr(entrega, "trabajador", None)),
        "obra": _obra_label(getattr(entrega, "obra", None)),
        "fecha_entrega": _fmt_date(getattr(entrega, "fecha_entrega", None)),
        "fecha_reposicion": _fmt_date(getattr(item, "fecha_reposicion_sugerida", None)),
    }


def _riesgo_operativo_score(alertas: list[dict[str, Any]]) -> dict[str, Any]:
    puntos = 100
    for alerta in alertas:
        nivel = alerta.get("nivel")
        count = int(alerta.get("count") or 0)
        if count <= 0:
            continue
        if nivel == "danger":
            puntos -= min(35, 8 + count * 2)
        elif nivel == "warning":
            puntos -= min(22, 5 + count)
        else:
            puntos -= min(12, 2 + count // 2)

    puntos = max(0, min(100, puntos))
    if puntos >= 90:
        return {"score": puntos, "label": "Controlado", "class": "success"}
    if puntos >= 70:
        return {"score": puntos, "label": "Con observaciones", "class": "warning"}
    return {"score": puntos, "label": "Requiere gestión", "class": "danger"}


def construir_panel_cumplimiento(user) -> dict[str, Any]:
    hoy = _hoy()
    in_30 = hoy + timedelta(days=VENTANA_ALERTA_DIAS)
    periodo_actual = periodo_from_date(hoy)

    parametro_actual = obtener_parametro_vigente(fecha=hoy, usar_fallback=False)
    parametro_referencial = parametro_actual or obtener_parametro_vigente(fecha=hoy, usar_fallback=True)
    sueldo_minimo = _decimal_or_none(getattr(parametro_referencial, "renta_minima_dependiente", None))

    contratos_vigentes = _contratos_vigentes_query(user)

    total_vigentes = contratos_vigentes.count()
    total_trabajadores_vigentes = (
        contratos_vigentes
        .enable_eagerloads(False)
        .with_entities(Contrato.trabajador_id)
        .distinct()
        .count()
    )

    contratos_vencidos_vigentes_q = contratos_vigentes.filter(
        Contrato.fecha_termino.isnot(None),
        Contrato.fecha_termino < hoy,
    )
    contratos_por_vencer_q = contratos_vigentes.filter(
        Contrato.fecha_termino.isnot(None),
        Contrato.fecha_termino >= hoy,
        Contrato.fecha_termino <= in_30,
    )
    contratos_42_q = contratos_vigentes.filter(
        Contrato.horas_semanales.isnot(None),
        Contrato.horas_semanales > 42,
    )
    contratos_sin_horas_q = contratos_vigentes.filter(Contrato.horas_semanales.is_(None))

    contratos_bajo_minimo_q = None
    contratos_bajo_minimo_count = 0
    if sueldo_minimo is not None:
        contratos_bajo_minimo_q = contratos_vigentes.filter(
            Contrato.sueldo_base.isnot(None),
            Contrato.sueldo_base < sueldo_minimo,
        )
        contratos_bajo_minimo_count = contratos_bajo_minimo_q.count()

    contratos_sin_sueldo_count = contratos_vigentes.filter(Contrato.sueldo_base.is_(None)).count()
    contratos_sin_datos_count = contratos_vigentes.filter(
        or_(
            Contrato.empleador_id.is_(None),
            Contrato.obra_id.is_(None),
            Contrato.cargo_id.is_(None),
            Contrato.fecha_inicio.is_(None),
        )
    ).count()

    prev_docs_base = _prev_docs_base_query(user).filter(PrevDocumentoPreventivo.estado != "ANULADO")
    docs_vencidos_q = prev_docs_base.filter(
        or_(
            PrevDocumentoPreventivo.estado == "VENCIDO",
            and_(
                PrevDocumentoPreventivo.fecha_vencimiento.isnot(None),
                PrevDocumentoPreventivo.fecha_vencimiento < hoy,
            ),
        )
    )
    docs_por_vencer_q = prev_docs_base.filter(
        PrevDocumentoPreventivo.fecha_vencimiento.isnot(None),
        PrevDocumentoPreventivo.fecha_vencimiento >= hoy,
        PrevDocumentoPreventivo.fecha_vencimiento <= in_30,
        PrevDocumentoPreventivo.estado != "VENCIDO",
    )

    epp_base = _epp_items_base_query(user).filter(PrevEntregaEPPItem.fecha_reposicion_sugerida.isnot(None))
    epp_vencido_q = epp_base.filter(PrevEntregaEPPItem.fecha_reposicion_sugerida < hoy)
    epp_por_vencer_q = epp_base.filter(
        PrevEntregaEPPItem.fecha_reposicion_sugerida >= hoy,
        PrevEntregaEPPItem.fecha_reposicion_sugerida <= in_30,
    )

    inicio_mes = hoy.replace(day=1)
    charlas_mes_count = _charlas_base_query(user).filter(PrevCharlaSeguridad.fecha >= inicio_mes, PrevCharlaSeguridad.fecha <= hoy).count()

    alertas: list[dict[str, Any]] = [
        {
            "id": "contratos_vencidos_vigentes",
            "nivel": "danger",
            "icono": "🚨",
            "titulo": "Contratos vigentes con fecha vencida",
            "count": contratos_vencidos_vigentes_q.count(),
            "detalle": "Contratos marcados como vigentes, pero con fecha de término anterior a hoy.",
            "accion": "Regularizar estado, extensión o desvinculación.",
            "url_key": "contratos_vencidos",
        },
        {
            "id": "contratos_por_vencer",
            "nivel": "warning",
            "icono": "⏳",
            "titulo": "Contratos por vencer",
            "count": contratos_por_vencer_q.count(),
            "detalle": f"Vencen dentro de los próximos {VENTANA_ALERTA_DIAS} días.",
            "accion": "Solicitar definición a jefatura y preparar anexo/carta según corresponda.",
            "url_key": "contratos_vencimientos",
        },
        {
            "id": "jornada_42",
            "nivel": "warning",
            "icono": "🕒",
            "titulo": "Jornadas sobre 42 horas",
            "count": contratos_42_q.count(),
            "detalle": "Contratos vigentes con horas semanales superiores a 42.",
            "accion": "Revisar jornada y, si corresponde, generar anexo masivo Ley 40 horas.",
            "url_key": "ley_40_horas",
        },
        {
            "id": "sueldo_minimo",
            "nivel": "danger" if contratos_bajo_minimo_count else "info",
            "icono": "💰",
            "titulo": "Sueldos base bajo mínimo parametrizado",
            "count": contratos_bajo_minimo_count,
            "detalle": "Comparación contra el parámetro laboral vigente o referencial cargado en el sistema.",
            "accion": "Revisar contratos y generar proceso de anexo masivo de sueldo mínimo si aplica.",
            "url_key": "sueldo_minimo",
        },
        {
            "id": "parametros_mes",
            "nivel": "warning",
            "icono": "📐",
            "titulo": "Parámetros laborales del mes",
            "count": 0 if parametro_actual else 1,
            "detalle": f"Período esperado: {periodo_actual}.",
            "accion": "Importar PDF Previred o registrar parámetros manualmente.",
            "url_key": "parametros",
        },
        {
            "id": "prev_docs_vencidos",
            "nivel": "danger",
            "icono": "🦺",
            "titulo": "Documentos preventivos vencidos",
            "count": docs_vencidos_q.count(),
            "detalle": "Documentación preventiva vencida o marcada como vencida.",
            "accion": "Actualizar documentos preventivos desde el módulo de prevención.",
            "url_key": "docs_prevencion_vencidos",
        },
        {
            "id": "prev_docs_por_vencer",
            "nivel": "warning",
            "icono": "📁",
            "titulo": "Documentos preventivos por vencer",
            "count": docs_por_vencer_q.count(),
            "detalle": f"Vencimientos preventivos dentro de {VENTANA_ALERTA_DIAS} días.",
            "accion": "Coordinar renovación documental antes del vencimiento.",
            "url_key": "docs_prevencion_por_vencer",
        },
        {
            "id": "epp_vencido",
            "nivel": "warning",
            "icono": "🥾",
            "titulo": "Reposiciones de EPP vencidas",
            "count": epp_vencido_q.count(),
            "detalle": "EPP con fecha sugerida de reposición ya cumplida.",
            "accion": "Revisar reposición y actualizar entrega si corresponde.",
            "url_key": "epp",
        },
    ]

    # Riesgo por obra: suma señales principales para priorizar gestión.
    obra_counter: Counter[str] = Counter()
    for c in contratos_vencidos_vigentes_q.limit(300).all():
        obra_counter[_obra_label(getattr(c, "obra", None))] += 3
    for c in contratos_por_vencer_q.limit(300).all():
        obra_counter[_obra_label(getattr(c, "obra", None))] += 2
    for c in contratos_42_q.limit(300).all():
        obra_counter[_obra_label(getattr(c, "obra", None))] += 2
    if contratos_bajo_minimo_q is not None:
        for c in contratos_bajo_minimo_q.limit(300).all():
            obra_counter[_obra_label(getattr(c, "obra", None))] += 3
    for doc in docs_vencidos_q.limit(300).all():
        obra_counter[_obra_label(getattr(doc, "obra", None))] += 3
    for doc in docs_por_vencer_q.limit(300).all():
        obra_counter[_obra_label(getattr(doc, "obra", None))] += 1

    top_obras = [
        {"obra": obra, "puntos": puntos, "nivel": "danger" if puntos >= 6 else "warning" if puntos >= 3 else "info"}
        for obra, puntos in obra_counter.most_common(8)
    ]

    score = _riesgo_operativo_score(alertas)
    alertas_con_gestion = sum(1 for alerta in alertas if int(alerta.get("count") or 0) > 0)

    return {
        "hoy": hoy,
        "in_30": in_30,
        "ventana_dias": VENTANA_ALERTA_DIAS,
        "periodo_actual": periodo_actual,
        "parametro_actual": parametro_actual,
        "parametro_referencial": parametro_referencial,
        "sueldo_minimo_fmt": _fmt_clp(sueldo_minimo),
        "score": score,
        "metricas": {
            "contratos_vigentes": total_vigentes,
            "trabajadores_vigentes": total_trabajadores_vigentes,
            "contratos_por_vencer": alertas[1]["count"],
            "contratos_vencidos_vigentes": alertas[0]["count"],
            "contratos_sobre_42": alertas[2]["count"],
            "contratos_sin_horas": contratos_sin_horas_q.count(),
            "contratos_bajo_minimo": contratos_bajo_minimo_count,
            "contratos_sin_sueldo": contratos_sin_sueldo_count,
            "contratos_sin_datos": contratos_sin_datos_count,
            "docs_prev_vencidos": alertas[5]["count"],
            "docs_prev_por_vencer": alertas[6]["count"],
            "epp_vencidos": alertas[7]["count"],
            "epp_por_vencer": epp_por_vencer_q.count(),
            "charlas_mes": charlas_mes_count,
            "alertas_con_gestion": alertas_con_gestion,
        },
        "alertas": alertas,
        "top_obras": top_obras,
        "listas": {
            "contratos_vencidos": [_contrato_row(c) for c in contratos_vencidos_vigentes_q.order_by(Contrato.fecha_termino.asc(), Contrato.id.asc()).limit(MAX_LISTA).all()],
            "contratos_por_vencer": [_contrato_row(c) for c in contratos_por_vencer_q.order_by(Contrato.fecha_termino.asc(), Contrato.id.asc()).limit(MAX_LISTA).all()],
            "contratos_42": [_contrato_row(c) for c in contratos_42_q.order_by(Contrato.horas_semanales.desc(), Contrato.id.desc()).limit(MAX_LISTA).all()],
            "contratos_bajo_minimo": (
                [_contrato_row(c, sueldo_minimo=sueldo_minimo) for c in contratos_bajo_minimo_q.order_by(Contrato.sueldo_base.asc(), Contrato.id.asc()).limit(MAX_LISTA).all()]
                if contratos_bajo_minimo_q is not None else []
            ),
            "docs_vencidos": [_doc_row(d) for d in docs_vencidos_q.order_by(PrevDocumentoPreventivo.fecha_vencimiento.asc(), PrevDocumentoPreventivo.id.asc()).limit(MAX_LISTA).all()],
            "docs_por_vencer": [_doc_row(d) for d in docs_por_vencer_q.order_by(PrevDocumentoPreventivo.fecha_vencimiento.asc(), PrevDocumentoPreventivo.id.asc()).limit(MAX_LISTA).all()],
            "epp_vencidos": [_epp_row(i) for i in epp_vencido_q.order_by(PrevEntregaEPPItem.fecha_reposicion_sugerida.asc(), PrevEntregaEPPItem.id.asc()).limit(MAX_LISTA).all()],
        },
        "acciones_rapidas": [
            {"icono": "📐", "label": "Parámetros laborales", "detalle": "Importar o revisar indicadores Previred.", "endpoint": "parametros_laborales.listado", "class": "btn-outline-primary", "requires": "admin.parametros"},
            {"icono": "🕒", "label": "Anexo 42 horas", "detalle": "Crear proceso masivo de ajuste de jornada.", "endpoint": "anexos_masivos.nuevo_ley_40_horas", "class": "btn-outline-warning", "requires": "documentos.editar"},
            {"icono": "💰", "label": "Anexo sueldo mínimo", "detalle": "Crear proceso masivo de reajuste de sueldo.", "endpoint": "anexos_masivos.nuevo_sueldo_minimo", "params": {"proceso": "2026-06-22"}, "class": "btn-outline-success", "requires": "documentos.editar"},
            {"icono": "🦺", "label": "Matriz preventiva", "detalle": "Ver semáforo preventivo por trabajador.", "endpoint": "prevencion_riesgos.matriz", "class": "btn-outline-secondary", "requires": "prevencion.ver"},
            {"icono": "🧭", "label": "Ley Karin", "detalle": "Ver protocolo operativo y checklist inicial.", "endpoint": "cumplimiento_laboral.ley_karin", "class": "btn-outline-danger", "requires": "reporteria.ver"},
        ],
    }
