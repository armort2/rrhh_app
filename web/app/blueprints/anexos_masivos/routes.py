# web/app/blueprints/anexos_masivos/routes.py
from __future__ import annotations

from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ...auth.decorators import role_required
from ...extensions import db
from ...models import Obra
from ...models.anexos_masivos import ProcesoAnexoMasivo
from ...services.anexos_masivos import (
    aplicar_cambios_proceso,
    crear_proceso_ley_40_horas,
    crear_proceso_reemplazo_dia,
    crear_proceso_sueldo_minimo,
    generar_documentos_proceso,
    marcar_detalles_proceso,
)
from . import bp


ARTICULO_TERCERO_S_MINIMO_20260622 = (
    "Por tratarse de un reajuste legal con efecto retroactivo a contar del 1 de mayo de 2026, "
    "el Empleador pagará en la liquidación de remuneraciones correspondiente al mes de junio de 2026 "
    "las diferencias de sueldo base que se hubieren devengado entre dicha fecha y la fecha de suscripción "
    "del presente anexo, calculadas conforme a la normativa vigente y considerando los períodos efectivamente trabajados."
)

PROCESOS_SUELDO_MINIMO = {
    "2026-01-14": {
        "key": "2026-01-14",
        "titulo": "Sueldo mínimo · proceso 14-01-2026",
        "nombre": "Ajuste sueldo mínimo 14-01-2026",
        "fecha_anexo": "2026-01-14",
        "fecha_vigencia": "2026-01-01",
        "horas_minimas": 40,
        "ley_s_minimo_nro": "21.751",
        "ley_s_minimo_fecha_publicacion": "2025-06-28",
        "sueldo_base_objetivo": "539000",
        "sueldo_base_actual_requerido": "",
        "modo_filtro_sueldo": "INFERIOR",
        "usar_articulo_tercero": False,
        "articulo_tercero_texto": "",
        "observaciones": "Proceso histórico de reajuste de sueldo mínimo enero 2026.",
        "alerta": "Proceso histórico: busca contratos vigentes con sueldo base inferior al objetivo informado.",
    },
    "2026-06-22": {
        "key": "2026-06-22",
        "titulo": "Sueldo mínimo · proceso 22-06-2026",
        "nombre": "Ajuste sueldo mínimo Ley 21.830 · 22-06-2026",
        "fecha_anexo": "2026-06-22",
        "fecha_vigencia": "2026-05-01",
        "horas_minimas": 0,
        "ley_s_minimo_nro": "21.830",
        "ley_s_minimo_fecha_publicacion": "2026-06-22",
        "sueldo_base_objetivo": "553553",
        "sueldo_base_actual_requerido": "539000",
        "modo_filtro_sueldo": "EXACTO",
        "usar_articulo_tercero": True,
        "articulo_tercero_texto": ARTICULO_TERCERO_S_MINIMO_20260622,
        "observaciones": "Filtro especial: contratos vigentes con sueldo base exactamente $539.000. Vigencia retroactiva desde mayo 2026.",
        "alerta": "Este proceso busca solo contratos vigentes con sueldo base exacto de $539.000 y los reajusta a $553.553.",
    },
}


def obras_visibles_query():
    q = Obra.query.filter(Obra.estado == "ACTIVA")
    if current_user.has_role("ADMIN"):
        return q

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return q.filter(db.text("1=0"))

    return q.filter(Obra.id.in_(obra_ids))


def assert_proceso_accessible_or_403(proceso: ProcesoAnexoMasivo) -> None:
    if current_user.has_role("ADMIN"):
        return

    obra_ids_usuario = {o.id for o in (current_user.obras or [])}
    obra_ids_detalle = {
        d.contrato.obra_id
        for d in (proceso.detalles or [])
        if d.contrato and d.contrato.obra_id is not None
    }

    if not obra_ids_detalle:
        return

    if not obra_ids_detalle.issubset(obra_ids_usuario):
        abort(403)


@bp.route("/")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    procesos = (
        ProcesoAnexoMasivo.query
        .order_by(ProcesoAnexoMasivo.id.desc())
        .all()
    )

    if not current_user.has_role("ADMIN"):
        obra_ids_usuario = {o.id for o in (current_user.obras or [])}
        filtrados = []

        for proceso in procesos:
            obra_ids_detalle = {
                d.contrato.obra_id
                for d in (proceso.detalles or [])
                if d.contrato and d.contrato.obra_id is not None
            }
            if not obra_ids_detalle or obra_ids_detalle.issubset(obra_ids_usuario):
                filtrados.append(proceso)

        procesos = filtrados

    return render_template("anexos_masivos/listado.html", procesos=procesos)


@bp.route("/nuevo/sueldo-minimo", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def nuevo_sueldo_minimo():
    obras = obras_visibles_query().order_by(Obra.nombre).all()
    preset_key = (request.form.get("preset_key") or request.args.get("proceso") or "").strip()
    preset = PROCESOS_SUELDO_MINIMO.get(preset_key)

    if request.method == "POST":
        try:
            nombre = (request.form.get("nombre") or "").strip()
            fecha_anexo = datetime.strptime(request.form["fecha_anexo"], "%Y-%m-%d").date()
            fecha_vigencia = datetime.strptime(request.form["fecha_vigencia"], "%Y-%m-%d").date()
            horas_minimas = int(request.form.get("horas_minimas") or 0)
            observaciones = (request.form.get("observaciones") or "").strip() or None
            obra_ids = request.form.getlist("obra_ids", type=int)

            ley_s_minimo_nro = (request.form.get("ley_s_minimo_nro") or "").strip() or None
            ley_s_minimo_fecha_publicacion_raw = (request.form.get("ley_s_minimo_fecha_publicacion") or "").strip()
            ley_s_minimo_fecha_publicacion = (
                datetime.strptime(ley_s_minimo_fecha_publicacion_raw, "%Y-%m-%d").date()
                if ley_s_minimo_fecha_publicacion_raw else None
            )

            sueldo_base_objetivo = (request.form.get("sueldo_base_objetivo") or "").strip() or None
            sueldo_base_actual_requerido = (request.form.get("sueldo_base_actual_requerido") or "").strip() or None
            modo_filtro_sueldo = (request.form.get("modo_filtro_sueldo") or "INFERIOR").strip().upper()

            usar_articulo_tercero = bool(request.form.get("usar_articulo_tercero"))
            articulo_tercero_texto = (request.form.get("articulo_tercero_texto") or "").strip() or None
            formato_generacion = (request.form.get("formato_generacion") or "AMBOS").strip().upper()

            if not nombre:
                raise ValueError("Debes indicar un nombre para el proceso.")

            if horas_minimas < 0:
                raise ValueError("Las horas semanales mínimas no pueden ser negativas.")

            if modo_filtro_sueldo == "EXACTO" and not sueldo_base_actual_requerido:
                raise ValueError("Para el filtro exacto debes indicar el sueldo base actual requerido.")

            if not current_user.has_role("ADMIN"):
                obra_ids_autorizadas = {o.id for o in (current_user.obras or [])}
                obra_ids = [oid for oid in obra_ids if oid in obra_ids_autorizadas]

            proceso = crear_proceso_sueldo_minimo(
                nombre=nombre,
                fecha_anexo=fecha_anexo,
                fecha_vigencia=fecha_vigencia,
                horas_minimas=horas_minimas,
                obra_ids=obra_ids or None,
                ley_s_minimo_nro=ley_s_minimo_nro,
                ley_s_minimo_fecha_publicacion=ley_s_minimo_fecha_publicacion,
                usar_articulo_tercero=usar_articulo_tercero,
                articulo_tercero_texto=articulo_tercero_texto,
                formato_generacion=formato_generacion,
                observaciones=observaciones,
                sueldo_base_objetivo=sueldo_base_objetivo,
                sueldo_base_actual_requerido=sueldo_base_actual_requerido,
                modo_filtro_sueldo=modo_filtro_sueldo,
            )

            if proceso.total_detalles == 0:
                flash(
                    "El proceso fue creado, pero no se encontraron trabajadores que cumplan las condiciones.",
                    "warning",
                )
            else:
                flash(
                    f"Proceso creado correctamente con {proceso.total_detalles} trabajador(es) candidato(s).",
                    "success",
                )

            return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")
        except Exception as e:
            db.session.rollback()
            flash(f"No fue posible crear el proceso: {e}", "error")

    return render_template(
        "anexos_masivos/form_sueldo_minimo.html",
        obras=obras,
        preset=preset,
        preset_key=preset_key,
        procesos_sueldo_minimo=PROCESOS_SUELDO_MINIMO,
    )

@bp.route("/nuevo/ley-40-horas", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def nuevo_ley_40_horas():
    obras = obras_visibles_query().order_by(Obra.nombre).all()

    if request.method == "POST":
        try:
            nombre = (request.form.get("nombre") or "").strip()
            fecha_anexo = datetime.strptime(request.form["fecha_anexo"], "%Y-%m-%d").date()
            fecha_vigencia = datetime.strptime(request.form["fecha_vigencia"], "%Y-%m-%d").date()
            horas_actuales_minimas = int(request.form.get("horas_actuales_minimas") or 44)
            horas_nuevas = int(request.form.get("horas_nuevas") or 42)
            observaciones = (request.form.get("observaciones") or "").strip() or None
            obra_ids = request.form.getlist("obra_ids", type=int)

            ley_40_hrs_nro = (request.form.get("ley_40_hrs_nro") or "").strip() or None
            ley_40_hrs_fecha_raw = (request.form.get("ley_40_hrs_fecha") or "").strip()
            ley_40_hrs_fecha = (
                datetime.strptime(ley_40_hrs_fecha_raw, "%Y-%m-%d").date()
                if ley_40_hrs_fecha_raw else None
            )

            formato_generacion = (request.form.get("formato_generacion") or "AMBOS").strip().upper()

            if not nombre:
                raise ValueError("Debes indicar un nombre para el proceso.")

            if horas_nuevas <= 0:
                raise ValueError("Las nuevas horas semanales deben ser mayores a 0.")

            if not current_user.has_role("ADMIN"):
                obra_ids_autorizadas = {o.id for o in (current_user.obras or [])}
                obra_ids = [oid for oid in obra_ids if oid in obra_ids_autorizadas]

            proceso = crear_proceso_ley_40_horas(
                nombre=nombre,
                fecha_anexo=fecha_anexo,
                fecha_vigencia=fecha_vigencia,
                horas_actuales_minimas=horas_actuales_minimas,
                horas_nuevas=horas_nuevas,
                obra_ids=obra_ids or None,
                ley_40_hrs_nro=ley_40_hrs_nro,
                ley_40_hrs_fecha=ley_40_hrs_fecha,
                formato_generacion=formato_generacion,
                observaciones=observaciones,
            )

            if proceso.total_detalles == 0:
                flash(
                    "El proceso fue creado, pero no se encontraron trabajadores que cumplan las condiciones.",
                    "warning",
                )
            else:
                flash(
                    f"Proceso creado correctamente con {proceso.total_detalles} trabajador(es) candidato(s).",
                    "success",
                )

            return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")

        except Exception as e:
            db.session.rollback()
            flash(f"No fue posible crear el proceso: {e}", "error")

    return render_template(
        "anexos_masivos/form_ley_40_horas.html",
        obras=obras,
    )



@bp.route("/nuevo/reemplazo-dia", methods=["GET", "POST"])
@role_required("ADMIN", "OPERADOR")
def nuevo_reemplazo_dia():
    obras = obras_visibles_query().order_by(Obra.nombre).all()

    if request.method == "POST":
        try:
            nombre = (request.form.get("nombre") or "").strip()
            fecha_anexo = datetime.strptime(request.form["fecha_anexo"], "%Y-%m-%d").date()
            fecha_trabajar = datetime.strptime(request.form["fecha_trabajar"], "%Y-%m-%d").date()
            fecha_reemplazar = datetime.strptime(request.form["fecha_reemplazar"], "%Y-%m-%d").date()
            observaciones = (request.form.get("observaciones") or "").strip() or None
            obra_ids = request.form.getlist("obra_ids", type=int)
            formato_generacion = (request.form.get("formato_generacion") or "AMBOS").strip().upper()

            if not nombre:
                raise ValueError("Debes indicar un nombre para el proceso.")

            if fecha_trabajar == fecha_reemplazar:
                raise ValueError("El día a trabajar y el día a reemplazar no pueden ser el mismo.")

            if not current_user.has_role("ADMIN"):
                obra_ids_autorizadas = {o.id for o in (current_user.obras or [])}
                obra_ids = [oid for oid in obra_ids if oid in obra_ids_autorizadas]

            proceso = crear_proceso_reemplazo_dia(
                nombre=nombre,
                fecha_anexo=fecha_anexo,
                fecha_trabajar=fecha_trabajar,
                fecha_reemplazar=fecha_reemplazar,
                obra_ids=obra_ids or None,
                formato_generacion=formato_generacion,
                observaciones=observaciones,
            )

            if proceso.total_detalles == 0:
                flash(
                    "El proceso fue creado, pero no se encontraron trabajadores vigentes para las obras seleccionadas.",
                    "warning",
                )
            else:
                flash(
                    f"Proceso creado correctamente con {proceso.total_detalles} trabajador(es) candidato(s).",
                    "success",
                )

            return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")

        except Exception as e:
            db.session.rollback()
            flash(f"No fue posible crear el proceso: {e}", "error")

    return render_template(
        "anexos_masivos/form_reemplazo_dia.html",
        obras=obras,
    )


@bp.route("/<int:proceso_id>")
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(proceso_id):
    proceso = ProcesoAnexoMasivo.query.get_or_404(proceso_id)
    assert_proceso_accessible_or_403(proceso)
    return render_template("anexos_masivos/detalle.html", proceso=proceso)


@bp.route("/<int:proceso_id>/seleccion", methods=["POST"])
@role_required("ADMIN", "OPERADOR")
def guardar_seleccion(proceso_id):
    proceso = ProcesoAnexoMasivo.query.get_or_404(proceso_id)
    assert_proceso_accessible_or_403(proceso)

    try:
        detalle_ids = request.form.getlist("detalle_ids", type=int)
        marcar_detalles_proceso(proceso, detalle_ids)
        flash("Selección actualizada correctamente.", "success")
    except Exception as e:
        flash(f"No fue posible actualizar la selección: {e}", "error")

    return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))


@bp.route("/<int:proceso_id>/generar", methods=["POST"])
@role_required("ADMIN", "OPERADOR")
def generar(proceso_id):
    proceso = ProcesoAnexoMasivo.query.get_or_404(proceso_id)
    assert_proceso_accessible_or_403(proceso)

    try:
        formato = (request.form.get("formato") or proceso.formato_generacion or "AMBOS").strip().upper()
        total_ok, total_error = generar_documentos_proceso(proceso, formato=formato)

        if total_error == 0:
            flash(f"Generación completada correctamente. Documentos generados: {total_ok}.", "success")
        else:
            flash(
                f"Generación terminada con observaciones. OK: {total_ok} · Error: {total_error}.",
                "warning",
            )
    except Exception as e:
        flash(f"No fue posible generar documentos del proceso: {e}", "error")

    return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))


@bp.route("/<int:proceso_id>/aplicar", methods=["POST"])
@role_required("ADMIN", "OPERADOR")
def aplicar(proceso_id):
    proceso = ProcesoAnexoMasivo.query.get_or_404(proceso_id)
    assert_proceso_accessible_or_403(proceso)

    try:
        total = aplicar_cambios_proceso(proceso)

        if proceso.tipo_proceso == "LEY_40_HORAS":
            flash(f"Se aplicaron {total} cambio(s) de jornada a contratos.", "success")
        elif proceso.tipo_proceso == "REEMPLAZO_DIA":
            flash(f"Se cerró documentalmente el acuerdo de reemplazo de día para {total} trabajador(es).", "success")
        else:
            flash(f"Se aplicaron {total} cambio(s) de sueldo base.", "success")

    except Exception as e:
        flash(f"No fue posible aplicar el proceso: {e}", "error")

    return redirect(url_for("anexos_masivos.detalle", proceso_id=proceso.id))