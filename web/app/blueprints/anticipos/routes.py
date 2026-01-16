# web/app/blueprints/anticipos/routes.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from sqlalchemy import func, and_, literal, case
from sqlalchemy.orm import aliased
from jinja2 import TemplateError

from ...extensions import db
from ...models import AnticipoNomina, AnticipoDetalle, Obra, Trabajador, Cargo, Contrato

# Mantengo importación para uso futuro (mes anterior por Excel, etc.)
from ...services.import_anticipos import import_anticipos_from_excel

from ...auth.decorators import role_required

bp = Blueprint("anticipos", __name__, url_prefix="/anticipos")


# ---------------------------
# Helpers
# ---------------------------
def _to_int(v: str | None) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() else None
    except Exception:
        return None


def _upper(v: str | None) -> str:
    return (v or "").strip().upper()


def _prev_period(anio: int, mes: int) -> Tuple[int, int]:
    if mes == 1:
        return anio - 1, 12
    return anio, mes - 1


def _format_nombre_completo(t: Trabajador) -> str:
    parts = [t.nombres, t.ap_paterno, (t.ap_materno or "")]
    return " ".join([p for p in parts if p and str(p).strip()]).strip()


def _rut_con_puntos(raw: str | None) -> str | None:
    """
    Formatea RUT a estilo chileno: 11.111.111-1
    Soporta entradas tipo:
      - "11399975-6"
      - "11399975"
      - "11.399.975-6"
    """
    if not raw:
        return None

    s = str(raw).strip()
    if not s:
        return None

    s = s.replace(".", "").replace(" ", "")
    dv = None

    if "-" in s:
        base, dv = s.split("-", 1)
        base = base.strip()
        dv = dv.strip()
    else:
        base = s

    # Base numérica
    base_digits = "".join(ch for ch in base if ch.isdigit())
    if not base_digits:
        return raw  # fallback

    # Insertar puntos cada 3 desde el final
    rev = base_digits[::-1]
    chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    base_fmt = ".".join(chunk[::-1] for chunk in chunks[::-1])

    if dv:
        return f"{base_fmt}-{dv}"
    return base_fmt


def _format_rut_show(t: Trabajador) -> str | None:
    rut = getattr(t, "rut", None)
    dv = getattr(t, "dv", None)
    if not rut:
        return None

    s = str(rut).strip().replace(".", "")
    if dv:
        return _rut_con_puntos(f"{s}-{dv}") or f"{s}-{dv}"
    return _rut_con_puntos(s) or s


def _ensure_nomina_origen(n: AnticipoNomina, default: str = "MANUAL") -> None:
    # Si aún no existe la columna en BD, no revienta.
    if hasattr(n, "origen"):
        if not getattr(n, "origen", None):
            setattr(n, "origen", default)


def _sync_detalles_desde_cc(nomina: AnticipoNomina) -> dict:
    """
    Inserta AnticipoDetalle faltantes para todos los trabajadores del CC.
    Etapa actual: incluye NO VIGENTES (no filtra por estado_trabajador).
    No borra ni pisa montos existentes.
    """
    cc = _upper(nomina.centro_costo)

    # trabajadores del CC: trabajadores.obra_id -> obras.centro_costo
    trabajadores_cc = (
        db.session.query(Trabajador, Obra)
        .join(Obra, Obra.id == Trabajador.obra_id)
        .filter(func.coalesce(Obra.centro_costo, "") == cc)
        .all()
    )

    existentes = {
        tid for (tid,) in (
            db.session.query(AnticipoDetalle.trabajador_id)
            .filter(AnticipoDetalle.nomina_id == nomina.id)
            .filter(AnticipoDetalle.trabajador_id.isnot(None))
            .all()
        )
    }

    insertados = 0
    for t, obra in trabajadores_cc:
        if t.id in existentes:
            continue

        d = AnticipoDetalle(
            nomina_id=nomina.id,
            trabajador_id=t.id,
            obra_id=obra.id if obra else None,
            rut=_format_rut_show(t),
            nombre_completo=_format_nombre_completo(t) or None,
            nombre_obra=obra.nombre if obra else None,
            centro_costo=cc,
            monto=0,
            observacion=None,
            estado_linea="OK",
        )
        db.session.add(d)
        insertados += 1

    db.session.commit()
    return {"nomina_id": nomina.id, "insertados": insertados, "total_cc": len(trabajadores_cc)}


def _tipo_key_expr():
    # Normaliza: upper(trim(coalesce(tipo, 'SIN TIPO')))
    return func.upper(func.trim(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO")))


def _tipo_priority_expr(tipo_key_expr):
    # 0 = primero (JEFATURA U OTROS), 1 = resto
    return case(
        (tipo_key_expr == "JEFATURA U OTROS", 0),
        else_=1,
    )


# ---------------------------
# Listado de nóminas
# ---------------------------
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR")
def listado():
    q_cc = _upper(request.args.get("centro_costo"))
    q_periodo = (request.args.get("periodo") or "").strip()  # "YYYY-MM"
    q_estado = _upper(request.args.get("estado"))

    q = AnticipoNomina.query

    if q_cc:
        q = q.filter(AnticipoNomina.centro_costo == q_cc)

    if q_periodo:
        try:
            anio = int(q_periodo.split("-")[0])
            mes = int(q_periodo.split("-")[1])
            q = q.filter(AnticipoNomina.anio == anio, AnticipoNomina.mes == mes)
        except Exception:
            flash("Período inválido. Use formato YYYY-MM (ej: 2026-01).", "warning")

    if q_estado:
        q = q.filter(AnticipoNomina.estado == q_estado)

    nominas = (
        q.order_by(AnticipoNomina.anio.desc(), AnticipoNomina.mes.desc(), AnticipoNomina.id.desc())
        .all()
    )

    centros = [
        r[0] for r in db.session.query(Obra.centro_costo)
        .filter(Obra.centro_costo.isnot(None))
        .distinct()
        .order_by(Obra.centro_costo.asc())
        .all()
    ]

    return render_template(
        "anticipos/anticipos_listado.html",
        nominas=nominas,
        centros=centros,
        q_cc=q_cc,
        q_periodo=q_periodo,
        q_estado=q_estado,
    )


# ---------------------------
# Nueva nómina (manual en sistema)
# ---------------------------
@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def nueva():
    centros = [
        r[0] for r in db.session.query(Obra.centro_costo)
        .filter(Obra.centro_costo.isnot(None))
        .distinct()
        .order_by(Obra.centro_costo.asc())
        .all()
    ]

    if request.method == "POST":
        cc = _upper(request.form.get("centro_costo"))
        anio = _to_int(request.form.get("anio"))
        mes = _to_int(request.form.get("mes"))

        if not cc or not anio or not mes:
            flash("Completa centro de costo, año y mes.", "error")
            return redirect(url_for("anticipos.nueva"))

        # Crear o abrir
        nomina = AnticipoNomina.query.filter_by(anio=anio, mes=mes, centro_costo=cc).first()
        if not nomina:
            nomina = AnticipoNomina(
                anio=anio,
                mes=mes,
                centro_costo=cc,
                estado="BORRADOR",
                origen_archivo=None,
                importado_por=current_user.id,
                importado_en=datetime.utcnow(),
            )
            _ensure_nomina_origen(nomina, "MANUAL")
            db.session.add(nomina)
            db.session.flush()
            db.session.commit()
            flash(f"Nómina creada (BORRADOR) #{nomina.id}.", "success")
        else:
            flash(f"Nómina existente #{nomina.id}. Se abrirá para edición.", "info")

        # Sincronizar trabajadores del CC
        res_sync = _sync_detalles_desde_cc(nomina)
        if res_sync.get("insertados", 0) > 0:
            flash(f"Se agregaron {res_sync['insertados']} trabajadores a la nómina (sincronización CC).", "success")

        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    # GET
    now = datetime.now()
    return render_template(
        "anticipos/anticipos_nueva.html",
        centros=centros,
        anio_default=now.year,
        mes_default=now.month,
    )


# ---------------------------
# Importar (se mantiene para futuro)
# ---------------------------
@bp.route("/importar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def importar():
    if request.method == "POST":
        filepath = (request.form.get("filepath") or "").strip()
        cc = _upper(request.form.get("centro_costo"))
        anio = _to_int(request.form.get("anio"))
        mes = _to_int(request.form.get("mes"))
        allow_reimport = (request.form.get("allow_reimport") == "1")

        if not filepath or not cc or not anio or not mes:
            flash("Completa archivo, centro de costo, año y mes.", "error")
            return redirect(url_for("anticipos.importar"))

        try:
            res = import_anticipos_from_excel(
                filepath=filepath,
                anio=anio,
                mes=mes,
                centro_costo=cc,
                user_id=current_user.id,
                allow_reimport=allow_reimport,
            )
        except Exception as e:
            flash(f"Error importando: {e}", "error")
            return redirect(url_for("anticipos.importar"))

        # Marcar origen si existe columna
        nomina = AnticipoNomina.query.get(res["nomina_id"])
        if nomina:
            _ensure_nomina_origen(nomina, "IMPORTADO")
            if hasattr(nomina, "origen"):
                nomina.origen = "IMPORTADO"
            db.session.commit()

        flash(
            f"Importación OK. Nómina #{res['nomina_id']} ({res['periodo']} · {res['centro_costo']}). "
            f"Filas: {res['stats']['filas']} · OK: {res['stats']['ok']}.",
            "success",
        )
        return redirect(url_for("anticipos.detalle", nomina_id=res["nomina_id"]))

    centros = [
        r[0] for r in db.session.query(Obra.centro_costo)
        .filter(Obra.centro_costo.isnot(None))
        .distinct()
        .order_by(Obra.centro_costo.asc())
        .all()
    ]
    return render_template("anticipos/anticipos_importar.html", centros=centros)


# ---------------------------
# Detalle nómina (planilla editable + mes anterior referencia)
# ---------------------------
@bp.route("/<int:nomina_id>", methods=["GET"])
@login_required
@role_required("ADMIN", "OPERADOR")
def detalle(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    # Opción: volver a sincronizar (por si faltan trabajadores nuevos)
    if (request.args.get("sync") or "") == "1" and nomina.estado == "BORRADOR":
        res_sync = _sync_detalles_desde_cc(nomina)
        if res_sync.get("insertados", 0) > 0:
            flash(f"Sync CC: se agregaron {res_sync['insertados']} trabajadores.", "success")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    q_text = (request.args.get("q") or "").strip()
    q_obra_id = _to_int(request.args.get("obra_id"))  # (opcional)
    q_tipo = (request.args.get("tipo_trabajador") or "").strip()
    q_cargo_id = _to_int(request.args.get("cargo_id"))  # ✅ NUEVO

    # Nómina mes anterior (misma CC)
    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    nomina_prev_id = nomina_prev.id if nomina_prev else None

    PrevDet = aliased(AnticipoDetalle)

    # Query planilla
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)

    # ✅ Contrato vigente: subquery para traer el último contrato VIGENTE por trabajador
    contrato_vigente_sq = (
        db.session.query(
            Contrato.trabajador_id.label("trabajador_id"),
            func.max(Contrato.id).label("contrato_id"),
        )
        .filter(Contrato.estado_contrato == "VIGENTE")
        .group_by(Contrato.trabajador_id)
        .subquery()
    )

    ContratoV = aliased(Contrato)

    q = (
        db.session.query(
            AnticipoDetalle,
            Cargo.nombre.label("cargo_nombre"),
            Trabajador.tipo_trabajador.label("tipo_trabajador"),
            Trabajador.ap_paterno.label("ap_paterno"),
            Trabajador.ap_materno.label("ap_materno"),
            Trabajador.nombres.label("nombres"),
            monto_prev_expr.label("monto_prev"),
            func.coalesce(ContratoV.sueldo_base, 0).label("sueldo_base"),  # ✅ NUEVO (desde contrato)
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .outerjoin(contrato_vigente_sq, contrato_vigente_sq.c.trabajador_id == Trabajador.id)
        .outerjoin(ContratoV, ContratoV.id == contrato_vigente_sq.c.contrato_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
            )
        )

    if q_obra_id:
        q = q.filter(AnticipoDetalle.obra_id == q_obra_id)

    if q_text:
        like = f"%{q_text}%"
        q = q.filter(
            (func.coalesce(AnticipoDetalle.rut, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.nombre_completo, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.nombre_obra, "").ilike(like))
            | (func.coalesce(Cargo.nombre, "").ilike(like))
            | (func.coalesce(Trabajador.tipo_trabajador, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.observacion, "").ilike(like))
        )

    if q_tipo:
        q = q.filter(func.coalesce(Trabajador.tipo_trabajador, "").ilike(q_tipo))

    if q_cargo_id:
        q = q.filter(Cargo.id == q_cargo_id)

    # Orden: JEFATURA U OTROS primero, luego resto
    tipo_key = _tipo_key_expr()
    tipo_prio = _tipo_priority_expr(tipo_key)

    rows = (
        q.order_by(
            tipo_prio.asc(),
            tipo_key.asc(),
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            AnticipoDetalle.nombre_completo.asc(),
        )
        .all()
    )

    detalles = []
    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev, sueldo_base in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()

        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "sueldo_base": float(sueldo_base or 0),  # ✅ NUEVO
            }
        )

    total_monto = (
        db.session.query(func.coalesce(func.sum(AnticipoDetalle.monto), 0))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    # Obras asociadas (filtro opcional)
    obras = (
        db.session.query(Obra.id, Obra.nombre)
        .join(AnticipoDetalle, AnticipoDetalle.obra_id == Obra.id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .distinct()
        .order_by(Obra.nombre.asc())
        .all()
    )

    # Tipos presentes
    tipos_trabajador = [
        r[0] for r in db.session.query(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO"))
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .distinct()
        .order_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").asc())
        .all()
    ]
    tipos_trabajador = [t for t in tipos_trabajador if t]

    # ✅ Cargos presentes (para dropdown)
    cargos = (
        db.session.query(Cargo.id, Cargo.nombre)
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .filter(Cargo.id.isnot(None))
        .distinct()
        .order_by(Cargo.nombre.asc())
        .all()
    )

    subtotales_tipo = (
        db.session.query(
            func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").label("tipo"),
            func.coalesce(func.sum(AnticipoDetalle.monto), 0).label("total"),
            func.count(AnticipoDetalle.id).label("cantidad"),
        )
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .group_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO"))
        .order_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").asc())
        .all()
    )

    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    return render_template(
        "anticipos/anticipos_detalle.html",
        nomina=nomina,
        detalles=detalles,
        total_monto=total_monto,
        obras=obras,
        tipos_trabajador=tipos_trabajador,
        cargos=cargos,
        subtotales_tipo=subtotales_tipo,
        q_text=q_text,
        q_obra_id=q_obra_id,
        q_tipo=q_tipo,
        q_cargo_id=q_cargo_id,
        nomina_prev=nomina_prev,
        periodo_prev_str=periodo_prev_str,
    )


# ---------------------------
# Guardar planilla (monto + observación)
# ---------------------------
@bp.post("/<int:nomina_id>/guardar")
@login_required
@role_required("ADMIN", "OPERADOR")
def guardar(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    if nomina.estado != "BORRADOR":
        flash("Solo se puede editar una nómina en estado BORRADOR.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    detalles_db = (
        AnticipoDetalle.query
        .filter_by(nomina_id=nomina.id)
        .all()
    )

    updated = 0
    for d in detalles_db:
        key_m = f"monto_{d.id}"
        key_o = f"obs_{d.id}"

        if key_m in request.form:
            raw = (request.form.get(key_m) or "").strip()
            raw = raw.replace(".", "").replace(",", "")
            try:
                monto = float(raw) if raw else 0
            except Exception:
                monto = 0
            d.monto = monto
            updated += 1

        if key_o in request.form:
            obs = (request.form.get(key_o) or "").strip() or None
            d.observacion = obs
            updated += 1

    db.session.commit()
    flash("Planilla guardada correctamente.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


# ---------------------------
# Copiar montos mes anterior (opcional)
# ---------------------------
@bp.post("/<int:nomina_id>/copiar_mes_anterior")
@login_required
@role_required("ADMIN", "OPERADOR")
def copiar_mes_anterior(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    if nomina.estado != "BORRADOR":
        flash("Solo se puede copiar desde mes anterior en estado BORRADOR.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()

    if not nomina_prev:
        flash("No existe nómina del mes anterior para este Centro de Costo.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    only_if_zero = (request.form.get("only_if_zero") or "1") == "1"

    PrevDet = aliased(AnticipoDetalle)

    pairs = (
        db.session.query(AnticipoDetalle, PrevDet.monto)
        .outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev.id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
            ),
        )
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .all()
    )

    copied = 0
    for det, monto_prev in pairs:
        if monto_prev is None:
            continue
        if only_if_zero and float(det.monto or 0) != 0:
            continue
        det.monto = monto_prev
        copied += 1

    if hasattr(nomina, "origen"):
        nomina.origen = "COPIADO"

    db.session.commit()
    flash(f"Copiado desde mes anterior: {copied} montos actualizados.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


# ---------------------------
# Acciones de flujo
# ---------------------------
@bp.post("/<int:nomina_id>/enviar_visacion")
@login_required
@role_required("ADMIN", "OPERADOR")
def enviar_visacion(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    if nomina.estado not in {"BORRADOR"}:
        flash("Solo se puede enviar a visación una nómina en estado BORRADOR.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    nomina.estado = "ENVIADA_A_VISACION"
    db.session.commit()
    flash("Nómina enviada a visación.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


@bp.post("/<int:nomina_id>/visar")
@login_required
@role_required("ADMIN")
def visar(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    if nomina.estado not in {"ENVIADA_A_VISACION", "BORRADOR"}:
        flash("La nómina no está en un estado visable.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    nomina.estado = "VISADA"
    nomina.visado_por = current_user.id
    nomina.visado_en = datetime.utcnow()
    db.session.commit()

    flash("Nómina visada correctamente.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


@bp.post("/<int:nomina_id>/revertir_borrador")
@login_required
@role_required("ADMIN")
def revertir_borrador(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    if nomina.estado == "BORRADOR":
        flash("La nómina ya está en BORRADOR.", "info")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    nomina.estado = "BORRADOR"
    db.session.commit()
    flash("Nómina revertida a BORRADOR. Edición habilitada.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


# ---------------------------
# Imprimible (HTML)
# ---------------------------
@bp.get("/<int:nomina_id>/imprimir")
@login_required
@role_required("ADMIN", "OPERADOR")
def imprimir(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    nomina_prev_id = nomina_prev.id if nomina_prev else None
    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    PrevDet = aliased(AnticipoDetalle)
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)

    q = (
        db.session.query(
            AnticipoDetalle,
            Cargo.nombre.label("cargo_nombre"),
            Trabajador.tipo_trabajador.label("tipo_trabajador"),
            Trabajador.ap_paterno.label("ap_paterno"),
            Trabajador.ap_materno.label("ap_materno"),
            Trabajador.nombres.label("nombres"),
            monto_prev_expr.label("monto_prev"),
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
            ),
        )

    tipo_key = _tipo_key_expr()
    tipo_prio = _tipo_priority_expr(tipo_key)

    rows = (
        q.order_by(
            tipo_prio.asc(),
            tipo_key.asc(),
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            func.coalesce(AnticipoDetalle.nombre_completo, "").asc(),
        )
        .all()
    )

    detalles = []
    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()

        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "rut_fmt": _rut_con_puntos(getattr(d, "rut", None)) or (getattr(d, "rut", None) or "-"),
            }
        )

    total_monto = (
        db.session.query(func.coalesce(func.sum(AnticipoDetalle.monto), 0))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    return render_template(
        "anticipos/anticipos_imprimir.html",
        nomina=nomina,
        detalles=detalles,
        total_monto=total_monto,
        nomina_prev=nomina_prev,
        periodo_prev_str=periodo_prev_str,
    )


# ---------------------------
# Imprimir PDF
# ---------------------------
@bp.get("/<int:nomina_id>/imprimir.pdf")
@login_required
@role_required("ADMIN", "OPERADOR")
def imprimir_pdf(nomina_id: int):
    """
    Motor de impresión PRO: genera PDF (Carta) con header/footer repetibles,
    paginación X/Y y control de saltos entre secciones.
    Requiere WeasyPrint + dependencias del sistema en el contenedor.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        flash(
            "Motor PDF no disponible (falta WeasyPrint o dependencias). "
            "Instala WeasyPrint en el contenedor para habilitar impresión PRO.",
            "error",
        )
        return redirect(url_for("anticipos.imprimir", nomina_id=nomina_id))

    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    # Mes anterior
    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    nomina_prev_id = nomina_prev.id if nomina_prev else None
    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    PrevDet = aliased(AnticipoDetalle)
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)

    q = (
        db.session.query(
            AnticipoDetalle,
            Cargo.nombre.label("cargo_nombre"),
            Trabajador.tipo_trabajador.label("tipo_trabajador"),
            Trabajador.ap_paterno.label("ap_paterno"),
            Trabajador.ap_materno.label("ap_materno"),
            Trabajador.nombres.label("nombres"),
            monto_prev_expr.label("monto_prev"),
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
            ),
        )

    tipo_key = _tipo_key_expr()
    tipo_prio = _tipo_priority_expr(tipo_key)

    rows = (
        q.order_by(
            tipo_prio.asc(),
            tipo_key.asc(),
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            func.coalesce(AnticipoDetalle.nombre_completo, "").asc(),
        )
        .all()
    )

    def format_rut(rut_str: str | None) -> str:
        if not rut_str:
            return "-"
        s = str(rut_str).strip()
        if "-" not in s:
            return s
        num, dv = s.split("-", 1)
        num = "".join(ch for ch in num if ch.isdigit())
        if not num:
            return s
        parts = []
        while len(num) > 3:
            parts.insert(0, num[-3:])
            num = num[:-3]
        parts.insert(0, num)
        return f"{'.'.join(parts)}-{dv.strip()}"

    detalles = []
    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip() or (d.nombre_completo or "-").strip()

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "rut_fmt": format_rut(getattr(d, "rut", None)),
            }
        )

    total_monto = (
        db.session.query(func.coalesce(func.sum(AnticipoDetalle.monto), 0))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    # Render HTML para PDF (template dedicado)
    try:
        html = render_template(
            "anticipos/anticipos_imprimir_pdf.html",
            nomina=nomina,
            detalles=detalles,
            total_monto=total_monto,
            nomina_prev=nomina_prev,
            periodo_prev_str=periodo_prev_str,
        )
    except TemplateError as e:
        flash(f"Error template impresión PDF: {e}", "error")
        return redirect(url_for("anticipos.imprimir", nomina_id=nomina_id))

    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    filename = f"anticipos_{nomina.id}_{nomina.anio:04d}-{nomina.mes:02d}_{nomina.centro_costo}.pdf".replace(" ", "_")
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'

    # Anti-caché fuerte (evita “PDF antiguo”)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Surrogate-Control"] = "no-store"

    return resp
