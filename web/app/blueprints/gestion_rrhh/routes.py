# web/app/blueprints/gestion_rrhh/routes.py
from __future__ import annotations

import csv
import io

from flask import Response, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.routing import BuildError

from ...auth.decorators import role_required
from ...services.gestion_rrhh import (
    construir_bandeja_gestion_rrhh,
    construir_plan_mensual_rrhh,
    filtrar_tareas,
)
from . import bp


ROLES_GESTION_RRHH_VER = (
    "ADMIN",
    "ADMINISTRATIVO",
    "JEFATURA",
    "PREVENCION",
    "FINANZAS",
    "SOLO_LECTURA",
    "OPERADOR",
    "REVISOR",
)


def _resolver_url(endpoint: str | None, params: dict | None) -> str | None:
    if not endpoint:
        return None
    try:
        return url_for(endpoint, **(params or {}))
    except (BuildError, TypeError, ValueError):
        return None


def _hidratar_urls(tareas: list[dict]) -> list[dict]:
    for tarea in tareas:
        tarea["url"] = _resolver_url(tarea.get("endpoint"), tarea.get("params"))
        tarea["secondary_url"] = _resolver_url(tarea.get("secondary_endpoint"), tarea.get("secondary_params"))
    return tareas


def _hidratar_plan_urls(plan: dict) -> dict:
    for grupo in plan.get("grupos", []) or []:
        _hidratar_urls(grupo.get("items", []) or [])
    for accion in plan.get("acciones_masivas", []) or []:
        accion["url"] = _resolver_url(accion.get("endpoint"), accion.get("params"))
    return plan


def _filtros_request() -> dict[str, str]:
    return {
        "prioridad": request.args.get("prioridad", "todas"),
        "categoria": request.args.get("categoria", "todas"),
        "q": request.args.get("q", ""),
    }


@bp.get("/")
@login_required
@role_required(*ROLES_GESTION_RRHH_VER)
def index():
    bandeja = construir_bandeja_gestion_rrhh(current_user)

    filtros = _filtros_request()
    tareas_filtradas = filtrar_tareas(bandeja["tareas"], **filtros)
    _hidratar_urls(tareas_filtradas)

    return render_template(
        "gestion_rrhh/index.html",
        bandeja=bandeja,
        tareas=tareas_filtradas,
        filtros=filtros,
    )


@bp.get("/exportar.csv")
@login_required
@role_required(*ROLES_GESTION_RRHH_VER)
def exportar_csv():
    bandeja = construir_bandeja_gestion_rrhh(current_user)
    filtros = _filtros_request()
    tareas = filtrar_tareas(bandeja["tareas"], **filtros)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Prioridad", "Categoria", "Estado", "Titulo", "Detalle", "Contexto", "Plazo"])
    for t in tareas:
        writer.writerow([
            t.get("prioridad_label", ""),
            t.get("categoria_label", ""),
            t.get("estado", ""),
            t.get("titulo", ""),
            t.get("detalle", ""),
            t.get("contexto", ""),
            t.get("dias_texto", ""),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bandeja_gestion_rrhh.csv"},
    )


@bp.get("/plan-mensual")
@login_required
@role_required(*ROLES_GESTION_RRHH_VER)
def plan_mensual():
    filtros = _filtros_request()
    plan = construir_plan_mensual_rrhh(current_user, **filtros)
    _hidratar_plan_urls(plan)

    return render_template(
        "gestion_rrhh/plan_mensual.html",
        plan=plan,
        filtros=filtros,
    )


@bp.get("/plan-mensual/exportar.csv")
@login_required
@role_required(*ROLES_GESTION_RRHH_VER)
def plan_mensual_exportar_csv():
    filtros = _filtros_request()
    plan = construir_plan_mensual_rrhh(current_user, **filtros)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Bloque",
        "Prioridad",
        "Categoria",
        "Estado",
        "Titulo",
        "Detalle",
        "Contexto",
        "Plazo",
        "Fecha objetivo",
    ])
    for grupo in plan.get("grupos", []) or []:
        for t in grupo.get("items", []) or []:
            fecha_objetivo = t.get("fecha_objetivo")
            writer.writerow([
                grupo.get("titulo", ""),
                t.get("prioridad_label", ""),
                t.get("categoria_label", ""),
                t.get("estado", ""),
                t.get("titulo", ""),
                t.get("detalle", ""),
                t.get("contexto", ""),
                t.get("dias_texto", ""),
                fecha_objetivo.strftime("%d-%m-%Y") if fecha_objetivo else "Sin fecha",
            ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=plan_mensual_rrhh.csv"},
    )
