# web/app/services/gestion_rrhh.py
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from .cumplimiento_laboral import construir_panel_cumplimiento


PRIORIDAD_RANK = {"alta": 1, "media": 2, "baja": 3}
PRIORIDAD_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
PRIORIDAD_CLASS = {"alta": "danger", "media": "warning", "baja": "info"}

CATEGORIA_LABEL = {
    "contratos": "Contratos",
    "jornada": "Jornada",
    "remuneraciones": "Remuneraciones",
    "prevencion": "Prevención",
    "parametros": "Parámetros",
    "datos": "Datos maestros",
}


def _int_or_zero(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except Exception:
        return 0


def _dias_texto(dias: int | None) -> str:
    if dias is None:
        return "Sin fecha límite"
    if dias < 0:
        return f"Vencido hace {abs(dias)} día(s)"
    if dias == 0:
        return "Vence hoy"
    return f"Vence en {dias} día(s)"


def _task(
    *,
    task_id: str,
    categoria: str,
    prioridad: str,
    icono: str,
    titulo: str,
    detalle: str,
    contexto: str = "",
    estado: str = "Pendiente",
    dias: int | None = None,
    endpoint: str | None = None,
    params: dict[str, Any] | None = None,
    action_label: str = "Gestionar",
    secondary_endpoint: str | None = "cumplimiento_laboral.index",
    secondary_params: dict[str, Any] | None = None,
    secondary_label: str = "Ver cumplimiento",
) -> dict[str, Any]:
    prioridad = prioridad if prioridad in PRIORIDAD_RANK else "media"
    categoria = categoria if categoria in CATEGORIA_LABEL else "datos"
    return {
        "id": task_id,
        "categoria": categoria,
        "categoria_label": CATEGORIA_LABEL[categoria],
        "prioridad": prioridad,
        "prioridad_label": PRIORIDAD_LABEL[prioridad],
        "prioridad_class": PRIORIDAD_CLASS[prioridad],
        "prioridad_rank": PRIORIDAD_RANK[prioridad],
        "icono": icono,
        "titulo": titulo,
        "detalle": detalle,
        "contexto": contexto,
        "estado": estado,
        "dias": dias,
        "dias_texto": _dias_texto(dias),
        "endpoint": endpoint,
        "params": params or {},
        "action_label": action_label,
        "secondary_endpoint": secondary_endpoint,
        "secondary_params": secondary_params or {},
        "secondary_label": secondary_label,
    }


def _contexto_contrato(row: dict[str, Any]) -> str:
    partes = [
        row.get("trabajador"),
        row.get("rut"),
        row.get("obra"),
        row.get("cargo"),
    ]
    return " · ".join(str(p).strip() for p in partes if p and str(p).strip() and str(p).strip() != "-")


def construir_bandeja_gestion_rrhh(user, *, max_por_bloque: int = 12) -> dict[str, Any]:
    """Construye una bandeja operativa a partir de señales ya disponibles.

    La Fase 5 no crea tablas nuevas: transforma alertas de cumplimiento en una
    lista de gestión priorizada, enlazando al módulo donde corresponde resolver
    cada caso.
    """
    panel = construir_panel_cumplimiento(user)
    listas = panel.get("listas", {}) or {}
    metricas = panel.get("metricas", {}) or {}
    tareas: list[dict[str, Any]] = []

    if not panel.get("parametro_actual"):
        tareas.append(_task(
            task_id="parametros-laborales-mes",
            categoria="parametros",
            prioridad="alta",
            icono="📐",
            titulo="Cargar parámetros laborales del mes",
            detalle=f"No hay parámetro laboral cargado para el período {panel.get('periodo_actual')}. Esto afecta controles de sueldo mínimo y cálculos dependientes.",
            contexto="Indicadores Previred / sueldo mínimo / topes previsionales",
            estado="Requiere carga",
            dias=0,
            endpoint="parametros_laborales.listado",
            action_label="Revisar parámetros",
        ))

    for row in (listas.get("contratos_vencidos") or [])[:max_por_bloque]:
        dias = row.get("dias_restantes")
        tareas.append(_task(
            task_id=f"contrato-vigente-vencido-{row.get('id')}",
            categoria="contratos",
            prioridad="alta",
            icono="🚨",
            titulo="Contrato vigente con fecha vencida",
            detalle=f"El contrato #{row.get('id')} figura vigente, pero su fecha de término es {row.get('fecha_termino')}.",
            contexto=_contexto_contrato(row),
            estado="Regularizar",
            dias=dias,
            endpoint="contratos.contrato_detalle",
            params={"contrato_id": row.get("id")},
            action_label="Abrir contrato",
        ))

    for row in (listas.get("contratos_por_vencer") or [])[:max_por_bloque]:
        dias = row.get("dias_restantes")
        prioridad = "alta" if dias is not None and dias <= 7 else "media"
        tareas.append(_task(
            task_id=f"contrato-por-vencer-{row.get('id')}",
            categoria="contratos",
            prioridad=prioridad,
            icono="⏳",
            titulo="Definir continuidad de contrato",
            detalle=f"Contrato #{row.get('id')} vence el {row.get('fecha_termino')}. Conviene definir extensión, término o paso a indefinido.",
            contexto=_contexto_contrato(row),
            estado="Por definir",
            dias=dias,
            endpoint="contratos.contrato_detalle",
            params={"contrato_id": row.get("id")},
            action_label="Ver contrato",
            secondary_endpoint="contratos_vencimientos.listado",
            secondary_label="Ver tablero",
        ))

    for row in (listas.get("contratos_42") or [])[:max_por_bloque]:
        tareas.append(_task(
            task_id=f"jornada-sobre-42-{row.get('id')}",
            categoria="jornada",
            prioridad="media",
            icono="🕒",
            titulo="Revisar jornada superior a 42 horas",
            detalle=f"Contrato #{row.get('id')} registra {row.get('horas_semanales')} horas semanales. Revisar si corresponde anexo de ajuste de jornada.",
            contexto=_contexto_contrato(row),
            estado="Revisar jornada",
            endpoint="contratos.contrato_detalle",
            params={"contrato_id": row.get("id")},
            action_label="Ver contrato",
            secondary_endpoint="anexos_masivos.nuevo_ley_40_horas",
            secondary_label="Crear anexo masivo",
        ))

    for row in (listas.get("contratos_bajo_minimo") or [])[:max_por_bloque]:
        tareas.append(_task(
            task_id=f"sueldo-bajo-minimo-{row.get('id')}",
            categoria="remuneraciones",
            prioridad="alta",
            icono="💰",
            titulo="Revisar sueldo base bajo mínimo",
            detalle=f"Contrato #{row.get('id')} tiene sueldo base {row.get('sueldo_base')} y brecha estimada {row.get('brecha_sueldo')} respecto del mínimo parametrizado.",
            contexto=_contexto_contrato(row),
            estado="Reajustar / validar",
            endpoint="contratos.contrato_detalle",
            params={"contrato_id": row.get("id")},
            action_label="Ver contrato",
            secondary_endpoint="anexos_masivos.nuevo_sueldo_minimo",
            secondary_params={"proceso": "2026-06-22"},
            secondary_label="Crear anexo masivo",
        ))

    for row in (listas.get("docs_vencidos") or [])[:max_por_bloque]:
        tareas.append(_task(
            task_id=f"doc-prev-vencido-{row.get('id')}",
            categoria="prevencion",
            prioridad="alta",
            icono="🦺",
            titulo="Documento preventivo vencido",
            detalle=f"{row.get('tipo')} figura vencido o requiere renovación. Fecha vencimiento: {row.get('fecha_vencimiento')}.",
            contexto=" · ".join(str(p) for p in [row.get("trabajador"), row.get("obra"), row.get("estado")] if p and p != "-"),
            estado="Renovar",
            endpoint="prevencion_riesgos.documento_detalle",
            params={"documento_id": row.get("id")},
            action_label="Ver documento",
            secondary_endpoint="prevencion_riesgos.documentos_listado",
            secondary_label="Ver prevención",
        ))

    for row in (listas.get("docs_por_vencer") or [])[:max_por_bloque]:
        tareas.append(_task(
            task_id=f"doc-prev-por-vencer-{row.get('id')}",
            categoria="prevencion",
            prioridad="media",
            icono="📁",
            titulo="Documento preventivo por vencer",
            detalle=f"{row.get('tipo')} vence el {row.get('fecha_vencimiento')}. Conviene coordinar renovación antes del vencimiento.",
            contexto=" · ".join(str(p) for p in [row.get("trabajador"), row.get("obra"), row.get("estado")] if p and p != "-"),
            estado="Programar renovación",
            endpoint="prevencion_riesgos.documento_detalle",
            params={"documento_id": row.get("id")},
            action_label="Ver documento",
            secondary_endpoint="prevencion_riesgos.documentos_listado",
            secondary_label="Ver prevención",
        ))

    for row in (listas.get("epp_vencidos") or [])[:max_por_bloque]:
        tareas.append(_task(
            task_id=f"epp-vencido-{row.get('entrega_id')}-{row.get('tipo')}",
            categoria="prevencion",
            prioridad="media",
            icono="🥾",
            titulo="Reposición de EPP vencida",
            detalle=f"{row.get('tipo')} tiene reposición sugerida para {row.get('fecha_reposicion')}.",
            contexto=" · ".join(str(p) for p in [row.get("trabajador"), row.get("obra")] if p and p != "-"),
            estado="Reponer / actualizar",
            endpoint="prevencion_riesgos.epp_detalle" if row.get("entrega_id") else "prevencion_riesgos.epp_listado",
            params={"entrega_id": row.get("entrega_id")} if row.get("entrega_id") else {},
            action_label="Ver entrega",
            secondary_endpoint="prevencion_riesgos.epp_listado",
            secondary_label="Ver EPP",
        ))

    datos_agregados = [
        ("contratos-sin-sueldo", "Contratos sin sueldo base", _int_or_zero(metricas.get("contratos_sin_sueldo")), "remuneraciones", "media", "💸", "Completar remuneración base."),
        ("contratos-sin-horas", "Contratos sin horas semanales", _int_or_zero(metricas.get("contratos_sin_horas")), "jornada", "media", "⏱️", "Completar horas semanales para auditoría de jornada."),
        ("contratos-sin-datos", "Contratos con datos maestros incompletos", _int_or_zero(metricas.get("contratos_sin_datos")), "datos", "media", "🧩", "Completar empleador, obra, cargo o fecha de inicio."),
    ]
    for key, titulo, count, categoria, prioridad, icono, detalle in datos_agregados:
        if count <= 0:
            continue
        tareas.append(_task(
            task_id=key,
            categoria=categoria,
            prioridad=prioridad,
            icono=icono,
            titulo=titulo,
            detalle=f"Hay {count} registro(s) que requieren depuración administrativa. {detalle}",
            contexto="Calidad de datos contractual",
            estado="Depurar",
            endpoint="cumplimiento_laboral.index",
            action_label="Ver cumplimiento",
        ))

    tareas.sort(key=lambda t: (t["prioridad_rank"], 9999 if t.get("dias") is None else t.get("dias"), t["categoria_label"], t["titulo"]))

    prioridad_counter = Counter(t["prioridad"] for t in tareas)
    categoria_counter = Counter(t["categoria"] for t in tareas)
    tareas_7 = sum(1 for t in tareas if t.get("dias") is not None and t["dias"] <= 7)

    return {
        "panel": panel,
        "fecha": date.today(),
        "tareas": tareas,
        "resumen": {
            "total": len(tareas),
            "alta": prioridad_counter.get("alta", 0),
            "media": prioridad_counter.get("media", 0),
            "baja": prioridad_counter.get("baja", 0),
            "proximos_7": tareas_7,
            "categorias": dict(categoria_counter),
        },
        "categorias": CATEGORIA_LABEL,
        "prioridades": PRIORIDAD_LABEL,
    }


def filtrar_tareas(
    tareas: list[dict[str, Any]],
    *,
    prioridad: str | None = None,
    categoria: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    prioridad = (prioridad or "todas").strip().lower()
    categoria = (categoria or "todas").strip().lower()
    needle = (q or "").strip().lower()

    filtradas = []
    for tarea in tareas:
        if prioridad != "todas" and tarea.get("prioridad") != prioridad:
            continue
        if categoria != "todas" and tarea.get("categoria") != categoria:
            continue
        if needle:
            haystack = " ".join(str(tarea.get(k, "")) for k in ("titulo", "detalle", "contexto", "estado")).lower()
            if needle not in haystack:
                continue
        filtradas.append(tarea)
    return filtradas



def _fecha_objetivo_desde_dias(hoy: date, dias: int | None) -> date | None:
    if dias is None:
        return None
    try:
        return hoy + timedelta(days=int(dias))
    except Exception:
        return None


def _bucket_plan_mensual(tarea: dict[str, Any]) -> str:
    dias = tarea.get("dias")
    if dias is None:
        return "sin_fecha"
    try:
        dias_int = int(dias)
    except Exception:
        return "sin_fecha"
    if dias_int <= 0:
        return "vencidos_hoy"
    if dias_int <= 7:
        return "semana_1"
    if dias_int <= 14:
        return "semana_2"
    if dias_int <= 30:
        return "mes"
    return "posterior"


PLAN_BUCKETS = [
    {
        "key": "vencidos_hoy",
        "icono": "🚨",
        "titulo": "Vencidos y gestiones de hoy",
        "descripcion": "Lo que conviene resolver antes de seguir abriendo nuevas tareas.",
        "class": "danger",
    },
    {
        "key": "semana_1",
        "icono": "📅",
        "titulo": "Próximos 7 días",
        "descripcion": "Gestión urgente de la semana: contratos, prevención y parámetros.",
        "class": "warning",
    },
    {
        "key": "semana_2",
        "icono": "🗓️",
        "titulo": "Semana siguiente",
        "descripcion": "Casos que aún permiten planificación antes del vencimiento.",
        "class": "info",
    },
    {
        "key": "mes",
        "icono": "📌",
        "titulo": "Resto del mes",
        "descripcion": "Seguimiento mensual para no llegar tarde al cierre.",
        "class": "secondary",
    },
    {
        "key": "sin_fecha",
        "icono": "🧩",
        "titulo": "Sin fecha límite directa",
        "descripcion": "Depuración, datos maestros o acciones permanentes que sostienen el sistema.",
        "class": "light",
    },
]


def _rutinas_rrhh_del_mes(bandeja: dict[str, Any]) -> list[dict[str, Any]]:
    """Checklist operativo mensual sin crear tablas nuevas.

    La idea es dejar una pauta visible para reunión semanal/cierre mensual. Se
    nutre del estado actual de la bandeja, pero no reemplaza los módulos
    transaccionales.
    """
    resumen = bandeja.get("resumen", {}) or {}
    categorias = resumen.get("categorias", {}) or {}
    panel = bandeja.get("panel", {}) or {}

    return [
        {
            "bloque": "Inicio de mes",
            "icono": "📐",
            "titulo": "Actualizar parámetros laborales",
            "detalle": "Revisar sueldo mínimo, topes imponibles, UF/UTM y parámetros previsionales antes de emitir cálculos masivos.",
            "estado": "OK" if panel.get("parametro_actual") else "Pendiente",
            "class": "success" if panel.get("parametro_actual") else "danger",
        },
        {
            "bloque": "Cada lunes",
            "icono": "⏳",
            "titulo": "Comité de contratos por vencer",
            "detalle": f"Revisar continuidad, anexos y cartas de aviso. Casos en bandeja: {categorias.get('contratos', 0)}.",
            "estado": "Revisar" if categorias.get("contratos", 0) else "Sin alertas",
            "class": "warning" if categorias.get("contratos", 0) else "success",
        },
        {
            "bloque": "Cada semana",
            "icono": "🕒",
            "titulo": "Control de jornada 42 horas",
            "detalle": f"Validar contratos con horas sobre estándar y preparar anexos cuando corresponda. Casos en bandeja: {categorias.get('jornada', 0)}.",
            "estado": "Revisar" if categorias.get("jornada", 0) else "OK",
            "class": "warning" if categorias.get("jornada", 0) else "success",
        },
        {
            "bloque": "Prevención",
            "icono": "🦺",
            "titulo": "Semáforo preventivo",
            "detalle": f"Coordinar documentos vencidos, por vencer y reposiciones de EPP. Casos en bandeja: {categorias.get('prevencion', 0)}.",
            "estado": "Gestionar" if categorias.get("prevencion", 0) else "Sin pendientes",
            "class": "warning" if categorias.get("prevencion", 0) else "success",
        },
        {
            "bloque": "Cierre mensual",
            "icono": "📤",
            "titulo": "Exportar evidencia de gestión",
            "detalle": "Descargar CSV de bandeja y plan mensual para respaldar revisión administrativa y seguimiento interno.",
            "estado": "Recomendado",
            "class": "info",
        },
    ]


def _acciones_masivas_sugeridas(bandeja: dict[str, Any]) -> list[dict[str, Any]]:
    categorias = ((bandeja.get("resumen", {}) or {}).get("categorias", {}) or {})
    acciones = []
    if categorias.get("jornada", 0):
        acciones.append({
            "icono": "🕒",
            "titulo": "Preparar anexo masivo 42 horas",
            "detalle": f"Hay {categorias.get('jornada', 0)} gestión(es) de jornada detectadas.",
            "endpoint": "anexos_masivos.nuevo_ley_40_horas",
            "label": "Crear anexo",
            "class": "warning",
        })
    if categorias.get("remuneraciones", 0):
        acciones.append({
            "icono": "💰",
            "titulo": "Revisar reajustes de remuneración",
            "detalle": f"Hay {categorias.get('remuneraciones', 0)} gestión(es) de sueldo o base remuneracional.",
            "endpoint": "anexos_masivos.nuevo_sueldo_minimo",
            "params": {"proceso": "2026-06-22"},
            "label": "Crear reajuste",
            "class": "success",
        })
    if categorias.get("contratos", 0):
        acciones.append({
            "icono": "⏳",
            "titulo": "Reunión de continuidad contractual",
            "detalle": f"Hay {categorias.get('contratos', 0)} gestión(es) contractuales para priorizar.",
            "endpoint": "contratos_vencimientos.listado",
            "label": "Ver vencimientos",
            "class": "primary",
        })
    if categorias.get("prevencion", 0):
        acciones.append({
            "icono": "🦺",
            "titulo": "Plan preventivo de renovación",
            "detalle": f"Hay {categorias.get('prevencion', 0)} gestión(es) preventivas o EPP en seguimiento.",
            "endpoint": "prevencion_riesgos.matriz",
            "label": "Ver matriz",
            "class": "danger",
        })
    return acciones


def construir_plan_mensual_rrhh(
    user,
    *,
    prioridad: str | None = None,
    categoria: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Construye una vista de seguimiento mensual desde la bandeja Fase 5.

    No persiste datos: ordena las tareas existentes por horizonte de atención y
    agrega rutinas/checklists para control periódico de RRHH.
    """
    hoy = date.today()
    bandeja = construir_bandeja_gestion_rrhh(user)
    tareas_filtradas = filtrar_tareas(
        bandeja.get("tareas", []),
        prioridad=prioridad,
        categoria=categoria,
        q=q,
    )

    grupos_map: dict[str, list[dict[str, Any]]] = {b["key"]: [] for b in PLAN_BUCKETS}
    grupos_map["posterior"] = []

    for tarea in tareas_filtradas:
        tarea = dict(tarea)
        tarea["fecha_objetivo"] = _fecha_objetivo_desde_dias(hoy, tarea.get("dias"))
        bucket = _bucket_plan_mensual(tarea)
        grupos_map.setdefault(bucket, []).append(tarea)

    grupos = []
    for meta in PLAN_BUCKETS:
        items = grupos_map.get(meta["key"], [])
        grupos.append({**meta, "items": items, "count": len(items)})

    posteriores = grupos_map.get("posterior", [])
    if posteriores:
        grupos.append({
            "key": "posterior",
            "icono": "🔭",
            "titulo": "Posterior a 30 días",
            "descripcion": "Tareas visibles que no requieren reacción inmediata, pero conviene mantener en radar.",
            "class": "secondary",
            "items": posteriores,
            "count": len(posteriores),
        })

    total_visible = len(tareas_filtradas)
    vencidas_hoy = len(grupos_map.get("vencidos_hoy", []))
    semana = len(grupos_map.get("semana_1", []))
    sin_fecha = len(grupos_map.get("sin_fecha", []))
    altas = sum(1 for t in tareas_filtradas if t.get("prioridad") == "alta")

    return {
        "fecha": hoy,
        "periodo_label": hoy.strftime("%m-%Y"),
        "bandeja": bandeja,
        "grupos": grupos,
        "tareas": tareas_filtradas,
        "rutinas": _rutinas_rrhh_del_mes(bandeja),
        "acciones_masivas": _acciones_masivas_sugeridas(bandeja),
        "resumen": {
            "total_visible": total_visible,
            "vencidas_hoy": vencidas_hoy,
            "semana": semana,
            "sin_fecha": sin_fecha,
            "altas": altas,
        },
        "categorias": CATEGORIA_LABEL,
        "prioridades": PRIORIDAD_LABEL,
    }
