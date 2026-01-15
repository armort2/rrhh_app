# web/app/blueprints/desvinculaciones/routes.py
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func

from ...extensions import db
from ...models import Trabajador, Contrato, CausalTermino, Desvinculacion
from ...utils import parse_date, parse_int

bp = Blueprint("desvinculaciones", __name__, url_prefix="/desvinculaciones")

from pathlib import Path

from ...services.paths_nextcloud import get_nc_paths
from ...services.storage_nextcloud_fs import ensure_dir
from ...services.desvinculaciones_docs import (
    build_carta_aviso_docx,
    build_finiquito_docx,
    make_pdf_from_docx,
)



# ---------------------------
# Helpers
# ---------------------------

_RUT_CLEAN_RE = re.compile(r"[^0-9kK]")


def _split_rut(raw: str) -> tuple[str, str]:
    """
    Normaliza un RUT desde string libre y devuelve (rut_digits, dv).
    Acepta: 12.345.678-9 / 12345678-9 / 123456789 (si el último es dv)
    """
    if not raw:
        return "", ""
    cleaned = _RUT_CLEAN_RE.sub("", str(raw)).upper()
    if len(cleaned) < 2:
        return "", ""
    dv = cleaned[-1]
    rut_digits = re.sub(r"\D", "", cleaned[:-1])
    if not rut_digits or not dv:
        return "", ""
    if not (dv.isdigit() or dv == "K"):
        return "", ""
    return rut_digits, dv


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_user() -> str:
    return str(getattr(current_user, "username", None) or getattr(current_user, "id", None) or "unknown")


def _push_meta(desv: Desvinculacion, key: str, payload: dict) -> None:
    """
    Guarda auditoría en meta de forma acumulativa.
    meta = { ... , key: [ {..}, {..} ] } o key: {..} si no existe.
    """
    meta = (desv.meta or {}) if hasattr(desv, "meta") else {}
    current = meta.get(key)

    entry = {"at": _now_utc_iso(), "by": _audit_user(), **payload}

    if current is None:
        meta[key] = [entry]
    elif isinstance(current, list):
        current.append(entry)
        meta[key] = current
    else:
        # Si antes era dict/string/etc, lo convertimos a lista
        meta[key] = [current, entry]

    if hasattr(desv, "meta"):
        desv.meta = meta

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9áéíóúñü]+", "-", s, flags=re.IGNORECASE)
    return s.strip("-") or "doc"


def _desv_base_filename(desv: Desvinculacion) -> str:
    t = desv.trabajador
    rut = (getattr(t, "rut_completo", None) or f"{t.rut}-{t.dv}").replace(".", "")
    nombre = _slug(f"{t.ap_paterno} {t.ap_materno} {t.nombres}")
    fterm = desv.fecha_termino.strftime("%Y-%m-%d") if desv.fecha_termino else "sin-fecha"
    return f"desv-{desv.id}_{rut}_{nombre}_{fterm}"


def _desv_target_dir(desv: Desvinculacion) -> Path:
    """
    Define carpeta destino en Nextcloud FS.
    Reutiliza get_nc_paths() para mantener un estándar corporativo.
    """
    paths = get_nc_paths()
    # Ajusta según tu implementación de get_nc_paths()
    # Idea: /.../Trabajadores/<RUT>/Desvinculaciones/
    t = desv.trabajador
    rut = (getattr(t, "rut_completo", None) or f"{t.rut}-{t.dv}").replace(".", "")
    base = Path(paths["trabajadores_root"])  # ejemplo: raíz trabajadores
    return base / rut / "Desvinculaciones"


def _get_contrato_vigente_actual(trabajador_id: int) -> Contrato | None:
    hoy = date.today()

    q = (
        Contrato.query
        .filter_by(trabajador_id=trabajador_id, estado_contrato="VIGENTE")
    )

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q = (
            q.filter(Contrato.fecha_inicio <= hoy)
             .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    return q.order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc()).first()


def _redirect_back_or(endpoint: str, **kwargs):
    next_url = (request.args.get("next") or request.form.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(endpoint, **kwargs))


# ---------------------------
# Listado (mejorado)
# ---------------------------

@bp.get("/")
@login_required
def listado():
    """
    Listado con filtros:
    - estado: BORRADOR / EMITIDA / ANULADA / (vacío = todos)
    - desde/hasta por fecha_termino
    - q: nombre/apellidos/rut/dv (tokens AND)
    """
    estado = (request.args.get("estado") or "").strip().upper()  # ""|BORRADOR|EMITIDA|ANULADA
    desde = parse_date(request.args.get("desde"))
    hasta = parse_date(request.args.get("hasta"))
    q_busqueda = (request.args.get("q") or "").strip()

    query = (
        Desvinculacion.query
        .join(Trabajador, Trabajador.id == Desvinculacion.trabajador_id)
        .join(CausalTermino, CausalTermino.id == Desvinculacion.causal_id)
    )

    if estado in {"BORRADOR", "EMITIDA", "ANULADA"}:
        query = query.filter(Desvinculacion.estado == estado)

    if desde:
        query = query.filter(Desvinculacion.fecha_termino >= desde)
    if hasta:
        query = query.filter(Desvinculacion.fecha_termino <= hasta)

    # Búsqueda por trabajador: tokens AND (permite "Nombre Apellido" en cualquier orden)
    if q_busqueda:
        tokens = [t for t in re.split(r"\s+", q_busqueda.strip()) if t]
        rut_digits, dv = _split_rut(q_busqueda)

        token_predicates = []
        for tok in tokens:
            like = f"%{tok}%"
            tok_digits = re.sub(r"\D", "", tok)

            ors = [
                Trabajador.nombres.ilike(like),
                Trabajador.ap_paterno.ilike(like),
                Trabajador.ap_materno.ilike(like),
                Trabajador.rut.ilike(like),
                Trabajador.dv.ilike(like),
            ]

            if tok_digits:
                ors.append(Trabajador.rut.ilike(f"%{tok_digits}%"))

            token_predicates.append(or_(*ors))

        if token_predicates:
            query = query.filter(and_(*token_predicates))

        # Refuerzo si viene RUT completo
        if rut_digits:
            query = query.filter(Trabajador.rut.ilike(f"%{rut_digits}%"))
        if dv:
            query = query.filter(Trabajador.dv.ilike(f"%{dv}%"))

    desvinculaciones = (
        query
        .order_by(Desvinculacion.id.desc())
        .limit(200)
        .all()
    )

    return render_template(
        "desvinculaciones/desvinculaciones_listado.html",
        desvinculaciones=desvinculaciones,
        filtro_estado=estado,
        filtro_desde=desde,
        filtro_hasta=hasta,
        q=q_busqueda,
    )


# ---------------------------
# Crear (MVP)
# ---------------------------

@bp.get("/trabajador/<int:trabajador_id>/nueva")
@login_required
def nueva_desvinculacion(trabajador_id: int):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    contrato_vigente = _get_contrato_vigente_actual(trabajador.id)
    if not contrato_vigente:
        flash("Este trabajador no tiene contrato vigente. No se puede iniciar una desvinculación.", "error")
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    causales = (
        CausalTermino.query
        .filter_by(activo=True)
        .order_by(CausalTermino.id.asc())
        .all()
    )

    return render_template(
        "desvinculaciones/desvinculacion_nueva.html",
        trabajador=trabajador,
        contrato=contrato_vigente,
        causales=causales,
    )


@bp.post("/trabajador/<int:trabajador_id>/crear")
@login_required
def crear_desvinculacion(trabajador_id: int):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    contrato_vigente = _get_contrato_vigente_actual(trabajador.id)
    if not contrato_vigente:
        flash("Este trabajador no tiene contrato vigente. No se puede crear la desvinculación.", "error")
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    causal_id = parse_int(request.form.get("causal_id"))
    fecha_termino = parse_date(request.form.get("fecha_termino"))
    fecha_aviso = parse_date(request.form.get("fecha_aviso"))
    motivo_detalle = (request.form.get("motivo_detalle") or "").strip() or None

    if not causal_id:
        flash("Debes seleccionar una causal de término.", "error")
        return redirect(url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id))

    causal = CausalTermino.query.get(causal_id)
    if not causal or not getattr(causal, "activo", False):
        flash("La causal seleccionada no es válida o está inactiva.", "error")
        return redirect(url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id))

    if not fecha_termino:
        flash("Debes indicar la fecha de término.", "error")
        return redirect(url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id))

    if fecha_aviso and fecha_aviso > fecha_termino:
        flash("La fecha de aviso no puede ser posterior a la fecha de término.", "error")
        return redirect(url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id))

    desv = Desvinculacion(
        trabajador_id=trabajador.id,
        contrato_id=contrato_vigente.id,
        empleador_id=getattr(contrato_vigente, "empleador_id", None),
        obra_id=getattr(contrato_vigente, "obra_id", None),
        causal_id=causal.id,
        fecha_aviso=fecha_aviso,
        fecha_termino=fecha_termino,
        motivo_detalle=motivo_detalle,
        estado="BORRADOR",
    )

    _push_meta(desv, "creacion", {"estado": "BORRADOR"})

    db.session.add(desv)
    db.session.commit()

    flash("Desvinculación creada en borrador.", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# ---------------------------
# Detalle
# ---------------------------

@bp.get("/<int:desvinculacion_id>")
@login_required
def detalle(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)
    return render_template("desvinculaciones/desvinculacion_detalle.html", desv=desv)


# ---------------------------
# Editar BORRADOR
# ---------------------------

@bp.get("/<int:desvinculacion_id>/editar")
@login_required
def editar(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado != "BORRADOR":
        flash("Solo puedes editar desvinculaciones en estado BORRADOR.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    causales = (
        CausalTermino.query
        .filter_by(activo=True)
        .order_by(CausalTermino.id.asc())
        .all()
    )

    return render_template(
        "desvinculaciones/desvinculacion_editar.html",
        desv=desv,
        causales=causales,
    )


@bp.post("/<int:desvinculacion_id>/editar")
@login_required
def editar_post(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado != "BORRADOR":
        flash("Solo puedes editar desvinculaciones en estado BORRADOR.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    causal_id = parse_int(request.form.get("causal_id"))
    fecha_termino = parse_date(request.form.get("fecha_termino"))
    fecha_aviso = parse_date(request.form.get("fecha_aviso"))
    motivo_detalle = (request.form.get("motivo_detalle") or "").strip() or None

    if not causal_id:
        flash("Debes seleccionar una causal de término.", "error")
        return redirect(url_for("desvinculaciones.editar", desvinculacion_id=desv.id))

    causal = CausalTermino.query.get(causal_id)
    if not causal or not getattr(causal, "activo", False):
        flash("La causal seleccionada no es válida o está inactiva.", "error")
        return redirect(url_for("desvinculaciones.editar", desvinculacion_id=desv.id))

    if not fecha_termino:
        flash("Debes indicar la fecha de término.", "error")
        return redirect(url_for("desvinculaciones.editar", desvinculacion_id=desv.id))

    if fecha_aviso and fecha_aviso > fecha_termino:
        flash("La fecha de aviso no puede ser posterior a la fecha de término.", "error")
        return redirect(url_for("desvinculaciones.editar", desvinculacion_id=desv.id))

    # Guardar snapshot antes/después en meta (simple y útil)
    before = {
        "causal_id": desv.causal_id,
        "fecha_termino": str(desv.fecha_termino) if desv.fecha_termino else None,
        "fecha_aviso": str(desv.fecha_aviso) if desv.fecha_aviso else None,
        "motivo_detalle": desv.motivo_detalle,
    }

    desv.causal_id = causal.id
    desv.fecha_termino = fecha_termino
    desv.fecha_aviso = fecha_aviso
    desv.motivo_detalle = motivo_detalle

    after = {
        "causal_id": desv.causal_id,
        "fecha_termino": str(desv.fecha_termino) if desv.fecha_termino else None,
        "fecha_aviso": str(desv.fecha_aviso) if desv.fecha_aviso else None,
        "motivo_detalle": desv.motivo_detalle,
    }

    _push_meta(desv, "ediciones", {"before": before, "after": after})

    db.session.commit()
    flash("Desvinculación actualizada (BORRADOR).", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# ---------------------------
# Emitir
# ---------------------------

@bp.post("/<int:desvinculacion_id>/emitir")
@login_required
def emitir(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado != "BORRADOR":
        flash("Solo puedes emitir desvinculaciones en estado BORRADOR.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    contrato = desv.contrato
    trabajador = desv.trabajador

    # Cerrar contrato (defensivo por columnas)
    if hasattr(contrato, "estado_contrato"):
        contrato.estado_contrato = "TERMINADO"

    if hasattr(contrato, "causal_termino"):
        contrato.causal_termino = desv.causal.causal_finiquito

    if hasattr(contrato, "fecha_finiquito"):
        contrato.fecha_finiquito = desv.fecha_termino

    # Si el contrato tiene fecha_termino, también la sellamos (si aplica)
    if hasattr(contrato, "fecha_termino") and getattr(contrato, "fecha_termino", None) is None:
        contrato.fecha_termino = desv.fecha_termino

    # Marcar trabajador no vigente
    if hasattr(trabajador, "estado_trabajador"):
        trabajador.estado_trabajador = "NO_VIGENTE"
    if hasattr(trabajador, "fecha_egreso_empresa"):
        trabajador.fecha_egreso_empresa = desv.fecha_termino

    desv.estado = "EMITIDA"

    _push_meta(desv, "emision", {"estado": "EMITIDA"})

    db.session.commit()

    flash("Desvinculación emitida. Contrato y trabajador actualizados.", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


@bp.post("/<int:desvinculacion_id>/generar-carta")
@login_required
def generar_carta(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    # Permitimos BORRADOR y EMITIDA (MVP). Si quieres restringir a EMITIDA, lo hacemos.
    if desv.estado not in {"BORRADOR", "EMITIDA"}:
        flash("Solo puedes generar documentos en BORRADOR o EMITIDA.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    target_dir = _desv_target_dir(desv)
    ensure_dir(target_dir)

    base = _desv_base_filename(desv)
    docx_name = f"{base}_carta-aviso.docx"
    pdf_name = f"{base}_carta-aviso.pdf"

    docx_path = target_dir / docx_name
    pdf_path = target_dir / pdf_name

    # Generación
    build_carta_aviso_docx(desv, docx_path)
    make_pdf_from_docx(docx_path, pdf_path)

    # Persistencia en modelo
    desv.carta_nombre = docx_name
    desv.carta_ruta = str(docx_path)
    _push_meta(desv, "doc_carta_aviso", {"docx": str(docx_path), "pdf": str(pdf_path), "estado": desv.estado})

    db.session.commit()

    flash("Carta de aviso generada (DOCX + PDF).", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


@bp.post("/<int:desvinculacion_id>/generar-finiquito")
@login_required
def generar_finiquito(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado not in {"BORRADOR", "EMITIDA"}:
        flash("Solo puedes generar documentos en BORRADOR o EMITIDA.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    target_dir = _desv_target_dir(desv)
    ensure_dir(target_dir)

    base = _desv_base_filename(desv)
    docx_name = f"{base}_finiquito.docx"
    pdf_name = f"{base}_finiquito.pdf"

    docx_path = target_dir / docx_name
    pdf_path = target_dir / pdf_name

    build_finiquito_docx(desv, docx_path)
    make_pdf_from_docx(docx_path, pdf_path)

    desv.finiquito_nombre = docx_name
    desv.finiquito_ruta = str(pdf_path)  # ojo: dejamos la ruta al PDF como "principal" para finiquito
    _push_meta(desv, "doc_finiquito", {"docx": str(docx_path), "pdf": str(pdf_path), "estado": desv.estado})

    db.session.commit()

    flash("Finiquito generado (DOCX + PDF).", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# ---------------------------
# Anular
# ---------------------------

@bp.post("/<int:desvinculacion_id>/anular")
@login_required
def anular(desvinculacion_id: int):
    """
    Anula una desvinculación.
    - Recomendación operativa: permitir anular BORRADOR y EMITIDA.
    - Por defecto NO revertimos contrato/trabajador automáticamente (evita "deshacer historia" sin control).
      Si luego quieres reversa, la hacemos como acción explícita y auditada.
    """
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado == "ANULADA":
        flash("Esta desvinculación ya está ANULADA.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    motivo = (request.form.get("motivo_anulacion") or "").strip()
    if not motivo:
        flash("Debes indicar un motivo de anulación.", "error")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    prev_estado = desv.estado
    desv.estado = "ANULADA"

    _push_meta(desv, "anulacion", {"prev_estado": prev_estado, "motivo": motivo})

    db.session.commit()

    flash("Desvinculación anulada.", "success")
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))
