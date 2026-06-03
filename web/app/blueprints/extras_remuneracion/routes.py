# web/app/blueprints/extras_remuneracion/routes.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from ...extensions import db
from ...models import (
    Obra, Trabajador, Contrato,
    ExtraRemuLote, ExtraRemuItem,
)
from ...services.extras_docs import generar_docx_y_pdf_extra_item
from ...services.extras_csv import export_csv_lote

from . import bp


# --------------------------
# Helpers
# --------------------------
def _to_int(v: str | None) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _to_decimal(v: str | None) -> Decimal:
    if not v:
        return Decimal("0")
    v = v.replace(".", "").replace(",", ".").strip()
    try:
        return Decimal(v)
    except Exception:
        return Decimal("0")

def _clp_int(d: Decimal) -> Decimal:
    """
    CLP sin decimales: redondeo a entero (0 decimales).
    """
    try:
        return d.quantize(Decimal("1"))
    except Exception:
        return Decimal(int(d))


def _calc_monto_trato(unidades: Decimal, valor_unidad: Decimal) -> Decimal:
    """
    Monto TRATO = unidades * valor_unidad (CLP entero).
    """
    if unidades is None or valor_unidad is None:
        return Decimal("0")
    if unidades < 0 or valor_unidad < 0:
        return Decimal("0")
    return _clp_int(unidades * valor_unidad)

def _centros_costos_accesibles_obras() -> list[Obra]:
    """
    ADMIN: todas
    Otros: obras asignadas al usuario (RBAC por obra).
    """
    q = Obra.query
    if not current_user.has_role("ADMIN"):
        ids = [o.id for o in (getattr(current_user, "obras", []) or [])]
        if not ids:
            return []
        q = q.filter(Obra.id.in_(ids))
    return q.order_by(Obra.codigo.asc(), Obra.nombre.asc()).all()


def _assert_access_obra(obra_id: int) -> None:
    if current_user.has_role("ADMIN"):
        return
    if not current_user.can_access_obra(obra_id):
        flash("No tienes acceso a esta obra/centro de costo.", "warning")
        raise PermissionError("obra_no_autorizada")


def _assert_access_cc(centro_costo: str) -> None:
    """
    RBAC conservador por CC:
    - ADMIN: ok
    - Otros: debe tener al menos 1 obra accesible cuyo centro_costo == centro_costo
    """
    if current_user.has_role("ADMIN"):
        return

    cc = (centro_costo or "").strip().upper()
    if not cc:
        flash("Centro de costo inválido.", "warning")
        raise PermissionError("cc_invalido")

    accesibles = getattr(current_user, "obras", []) or []
    for o in accesibles:
        o_cc = (getattr(o, "centro_costo", "") or "").strip().upper()
        if o_cc == cc:
            return

    flash("No tienes acceso a este centro de costo.", "warning")
    raise PermissionError("cc_no_autorizado")


def _period_bounds(anio: int, mes: int) -> tuple[date, date]:
    """
    Retorna (inicio_mes, inicio_mes_siguiente) como límites [inicio, siguiente)
    """
    inicio = date(anio, mes, 1)
    if mes == 12:
        siguiente = date(anio + 1, 1, 1)
    else:
        siguiente = date(anio, mes + 1, 1)
    return inicio, siguiente

def _clp_sin_decimales(v) -> str:
    try:
        n = int(Decimal(str(v or 0)))
    except Exception:
        n = 0
    return f"${f'{n:,}'.replace(',', '.')}"

def _pretty_bono_codigo(codigo: str) -> str:
    """
    Convierte BONO_DESEMPENO -> Bono desempeño, etc.
    (Mis­ma lógica 'humana' que usamos en docs.)
    """
    c = (codigo or "").strip()
    if not c:
        return ""

    mapa = {
        "BONO_PRODUCCION": "Bono de producción",
        "BONO_DESEMPENO": "Bono desempeño",
        "BONO_ASISTENCIA": "Bono asistencia",
        "BONO_RESPONSABILIDAD": "Bono de responsabilidad",
        "BONO_SEGURIDAD": "Bono seguridad",
        "BONO_TURNOS": "Bono por turnos",
        "BONO_PUNTUALIDAD": "Bono puntualidad",
        "BONO_EXTRAORDINARIO": "Bono extraordinario",
    }
    c_u = c.upper()
    if c_u in mapa:
        return mapa[c_u]

    # fallback "bonito" para códigos nuevos
    return c.replace("_", " ").strip().capitalize()

def _contrato_solapa_periodo(c: Contrato, inicio: date, siguiente: date) -> bool:
    """
    Determina si el contrato solapa el mes:
    - inicio_contrato < inicio_mes_siguiente
    - termino_contrato es NULL o termino_contrato >= inicio_mes
    """
    fi = getattr(c, "fecha_inicio", None)
    ft = getattr(c, "fecha_termino", None)

    if not fi:
        return False

    # fi < siguiente
    if fi >= siguiente:
        return False

    # ft is None OR ft >= inicio
    if ft is None:
        return True
    return ft >= inicio


def _requiere_anexo_default(concepto_ui: str) -> bool:
    c = (concepto_ui or "").strip().upper()
    return c in {"BONO", "TRATO", "SABADO", "HORAS_EXTRA"}


def _map_concepto_ui_a_tipo_y_codigo(concepto_ui: str) -> tuple[str, str]:
    """
    UI entrega: BONO/TRATO/SABADO/HORAS_EXTRA/OTRO
    DB guarda: concepto_tipo (BONO/TRATO/JORNADA_EXTRAORDINARIA) + concepto_codigo
    """
    c = (concepto_ui or "").strip().upper()

    if c == "TRATO":
        return ("TRATO", "TRATO")

    if c in {"SABADO", "SÁBADO"}:
        return ("JORNADA_EXTRAORDINARIA", "SABADO")

    if c in {"HORAS_EXTRA", "HORA_EXTRA", "HORAS EXTRAS", "HORAS-EXTRA"}:
        return ("JORNADA_EXTRAORDINARIA", "HORAS_EXTRA")

    if c == "OTRO":
        return ("BONO", "OTRO")

    # default BONO
    return ("BONO", "BONO")


def _set_estado_doc_por_formato(item: ExtraRemuItem) -> None:
    """
    Mantiene estado_doc consistente con el formato y rutas generadas.
    """
    formato = (getattr(item, "formato", "") or "AMBOS").upper()
    docx_ok = bool(getattr(item, "docx_ruta", None))
    pdf_ok = bool(getattr(item, "pdf_ruta", None))

    if formato == "DOCX":
        item.estado_doc = "DOCX_GENERADO" if docx_ok else "PENDIENTE"
    elif formato == "PDF":
        item.estado_doc = "PDF_GENERADO" if pdf_ok else "PENDIENTE"
    else:
        item.estado_doc = "AMBOS_GENERADO" if (docx_ok and pdf_ok) else "PENDIENTE"


def _trabajadores_con_contrato_vigente_en_mes(cc: str, anio: int, mes: int) -> list[Trabajador]:
    """
    Retorna trabajadores que tuvieron contrato vigente (solape) en el periodo del lote,
    filtrando por centro de costo (via Obra del contrato).
    Incluye desvinculados dentro del mes (solape parcial).
    """
    cc_u = (cc or "").strip().upper()
    inicio, siguiente = _period_bounds(anio, mes)

    # 1) Subquery: IDs únicos de trabajadores elegibles
    subq = (
        db.session.query(Trabajador.id.label("trabajador_id"))
        .join(Contrato, Contrato.trabajador_id == Trabajador.id)
        .join(Obra, Obra.id == Contrato.obra_id)
        .filter(Obra.centro_costo == cc_u)
        .filter(Contrato.fecha_inicio < siguiente)
        .filter((Contrato.fecha_termino.is_(None)) | (Contrato.fecha_termino >= inicio))
        .distinct()
        .subquery()
    )

    # 2) Query final: traemos Trabajador y ordenamos por apellido/nombre (sin DISTINCT ON conflictivo)
    q = (
        Trabajador.query
        .join(subq, subq.c.trabajador_id == Trabajador.id)
        .order_by(
            Trabajador.ap_paterno.asc(),
            Trabajador.ap_materno.asc(),
            Trabajador.nombres.asc(),
        )
    )

    return q.all()


def _obras_del_cc_accesibles(cc: str) -> list[Obra]:
    """
    Lista de obras del CC (solo accesibles si no es ADMIN).
    Útil para que el lote tenga un obra_id representativo (fallback/UI).
    """
    cc_u = (cc or "").strip().upper()
    q = Obra.query.filter(Obra.centro_costo == cc_u)
    if not current_user.has_role("ADMIN"):
        ids = [o.id for o in (getattr(current_user, "obras", []) or [])]
        if not ids:
            return []
        q = q.filter(Obra.id.in_(ids))
    return q.order_by(Obra.codigo.asc(), Obra.nombre.asc()).all()


def _pick_obra_id_representativa(cc: str, obra_id_form: int | None) -> int | None:
    """
    Deja un obra_id 'representativo' (para RBAC/UX), pero el lote se gobierna por CC.
    Priorizamos la obra seleccionada si pertenece al mismo CC.
    """
    cc_u = (cc or "").strip().upper()

    if obra_id_form:
        obra = Obra.query.get(obra_id_form)
        if obra:
            o_cc = (getattr(obra, "centro_costo", "") or "").strip().upper()
            if o_cc == cc_u:
                # Validamos acceso (si no es admin)
                _assert_access_obra(obra.id)
                return obra.id

    # Fallback: primera obra accesible del CC
    obras = _obras_del_cc_accesibles(cc_u)
    if obras:
        return obras[0].id

    return None


def _sugerir_contrato_para_item(trabajador_id: int, cc: str, anio: int, mes: int) -> Contrato | None:
    """
    Sugerimos un contrato que:
    - sea del trabajador
    - pertenezca a una obra del mismo CC
    - solape con el mes del lote
    Preferimos:
      1) estado_contrato == 'VIGENTE' y solapa
      2) cualquier contrato que solape
    """
    cc_u = (cc or "").strip().upper()
    inicio, siguiente = _period_bounds(anio, mes)

    # Candidatos que solapan y están en el CC
    q = (
        Contrato.query
        .join(Obra, Obra.id == Contrato.obra_id)
        .filter(Contrato.trabajador_id == trabajador_id)
        .filter(Obra.centro_costo == cc_u)
        .filter(Contrato.fecha_inicio < siguiente)
        .filter((Contrato.fecha_termino.is_(None)) | (Contrato.fecha_termino >= inicio))
    )

    # Preferimos vigentes
    c = (
        q.filter(Contrato.estado_contrato == "VIGENTE")
        .order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc())
        .first()
    )
    if c:
        return c

    return q.order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc()).first()


# --------------------------
# Vistas
# --------------------------
@bp.get("/")
@login_required
def listado():
    # Importante: ahora filtramos por CC, pero mantenemos obra_id como filtro UI si quieres.
    obra_id = _to_int(request.args.get("obra_id"))
    estado = (request.args.get("estado") or "").strip().upper()
    periodo = (request.args.get("periodo") or "").strip()  # YYYY-MM

    obras = _centros_costos_accesibles_obras()

    query = ExtraRemuLote.query

    if obra_id:
        _assert_access_obra(obra_id)
        obra = Obra.query.get(obra_id)
        if obra:
            cc = (obra.centro_costo or "").strip().upper()
            if cc:
                query = query.filter(ExtraRemuLote.centro_costo == cc)

    if estado in {"BORRADOR", "ENVIADO", "APROBADO", "CERRADO", "EXPORTADO"}:
        query = query.filter(ExtraRemuLote.estado == estado)

    if periodo and len(periodo) == 7 and "-" in periodo:
        try:
            anio = int(periodo.split("-")[0])
            mes = int(periodo.split("-")[1])
            query = query.filter(ExtraRemuLote.anio == anio, ExtraRemuLote.mes == mes)
        except Exception:
            pass

    lotes = query.order_by(ExtraRemuLote.id.desc()).limit(200).all()

    return render_template(
        "extras_remuneracion/listado.html",
        obras=obras,
        lotes=lotes,
        obra_id=obra_id,
        estado=estado,
        periodo=periodo,
    )


@bp.get("/nuevo")
@login_required
def nuevo():
    obras = _centros_costos_accesibles_obras()
    hoy = date.today()
    return render_template(
        "extras_remuneracion/lote_nuevo.html",
        obras=obras,
        anio=hoy.year,
        mes=hoy.month,
    )


@bp.post("/crear")
@login_required
def crear():
    cc = (request.form.get("centro_costo") or "").strip().upper()
    obra_id = _to_int(request.form.get("obra_id"))
    anio = _to_int(request.form.get("anio"))
    mes = _to_int(request.form.get("mes"))

    if not cc:
        flash("Debes seleccionar un centro de costo.", "warning")
        return redirect(url_for("extras_remuneracion.nuevo"))

    if not obra_id:
        flash("Debes seleccionar una obra.", "warning")
        return redirect(url_for("extras_remuneracion.nuevo"))

    if not anio or not mes or mes < 1 or mes > 12:
        flash("Periodo inválido.", "warning")
        return redirect(url_for("extras_remuneracion.nuevo"))

    # RBAC por CC (conservador)
    _assert_access_cc(cc)

    # Validar obra seleccionada
    obra = Obra.query.get_or_404(obra_id)

    # Validar acceso por obra (mantiene tu RBAC actual)
    _assert_access_obra(obra.id)

    # Validar que la obra pertenezca al CC seleccionado
    obra_cc = (obra.centro_costo or obra.codigo or "").strip().upper()
    if obra_cc != cc:
        flash("La obra seleccionada no pertenece al centro de costo indicado.", "warning")
        return redirect(url_for("extras_remuneracion.nuevo"))

    # EXISTENCIA: CC + periodo
    existe = (
        ExtraRemuLote.query
        .filter(
            ExtraRemuLote.centro_costo == cc,
            ExtraRemuLote.anio == anio,
            ExtraRemuLote.mes == mes,
        )
        .first()
    )
    if existe:
        flash("Ya existe un lote para ese centro de costo y periodo.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=existe.id))

    # obra_id representativo = la obra elegida (queda perfecto para trazabilidad)
    lote = ExtraRemuLote(
        obra_id=obra.id,
        centro_costo=cc,
        anio=anio,
        mes=mes,
        estado="BORRADOR",
        creado_por_user_id=getattr(current_user, "id", None),
    )

    db.session.add(lote)
    db.session.commit()

    flash("Lote creado.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

@bp.get("/<int:lote_id>")
@login_required
def detalle(lote_id: int):
    lote = ExtraRemuLote.query.get_or_404(lote_id)
    _assert_access_cc(lote.centro_costo)

    trabajadores = _trabajadores_con_contrato_vigente_en_mes(lote.centro_costo, lote.anio, lote.mes)

    hoy = date.today()
    trab_meta: dict[int, dict] = {}

    vigentes_hoy_ids = {
        tid for (tid,) in (
            db.session.query(Contrato.trabajador_id)
            .filter(
                Contrato.fecha_inicio <= hoy,
                (Contrato.fecha_termino.is_(None)) | (Contrato.fecha_termino >= hoy),
            )
            .distinct()
            .all()
        )
    }

    for t in trabajadores:
        trab_meta[t.id] = {"no_vigente_hoy": (t.id not in vigentes_hoy_ids)}

    # ✅ Total sin decimales y en CLP
    total_num = sum((it.monto or Decimal("0")) for it in (lote.items or []))
    total = _clp_sin_decimales(total_num)

    # ✅ View-model para tabla (montos y concepto "bonito")
    items_vm = []
    for it in (lote.items or []):
        concepto_codigo_raw = (it.concepto_codigo or "")
        concepto_tipo = (it.concepto_tipo or "")

        concepto_codigo_label = concepto_codigo_raw
        if (concepto_tipo or "").strip().upper() == "BONO":
            # el código del bono se muestra "humano"
            concepto_codigo_label = _pretty_bono_codigo(concepto_codigo_raw)

        items_vm.append({
            "it": it,
            "monto_clp": _clp_sin_decimales(it.monto),
            "concepto_codigo_label": concepto_codigo_label,
        })

    return render_template(
        "extras_remuneracion/lote_detalle.html",
        lote=lote,
        trabajadores=trabajadores,
        total=total,
        trab_meta=trab_meta,
        items_vm=items_vm,   # 👈 nuevo
    )

@bp.post("/<int:lote_id>/agregar-item")
@login_required
def agregar_item(lote_id: int):
    lote = ExtraRemuLote.query.get_or_404(lote_id)
    _assert_access_cc(lote.centro_costo)

    if lote.estado in {"CERRADO", "EXPORTADO"}:
        flash("El lote está cerrado/exportado. No se puede modificar.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    trabajador_id = _to_int(request.form.get("trabajador_id"))
    contrato_id = _to_int(request.form.get("contrato_id"))
    concepto_ui = (request.form.get("concepto") or "").strip().upper()

    # Monto (para conceptos NO-TRATO). Para TRATO lo recalculamos.
    monto = _to_decimal(request.form.get("monto"))

    # TRATO (Opción B)
    unidades = _to_decimal(request.form.get("unidades"))
    valor_unidad = _to_decimal(request.form.get("valor_unidad"))

    resena = (request.form.get("resena") or "").strip()
    imponible = (request.form.get("imponible") or "1").strip() == "1"
    formato = (request.form.get("formato") or "AMBOS").strip().upper()

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    if concepto_ui not in {"BONO", "TRATO", "SABADO", "HORAS_EXTRA", "OTRO"}:
        flash("Concepto inválido.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    codigo_interno = (request.form.get("codigo_bono") or "").strip()

    if not resena or len(resena) < 10:
        flash("Debes indicar una reseña (mínimo 10 caracteres).", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    if formato not in {"DOCX", "PDF", "AMBOS"}:
        formato = "AMBOS"

    # --- TRATO: monto calculado (Opción B) ---
    if concepto_ui == "TRATO":
        if unidades <= 0:
            flash("Debes indicar unidades (> 0) para TRATO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        if valor_unidad <= 0:
            flash("Debes indicar valor por unidad (> 0) para TRATO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        monto = _calc_monto_trato(unidades, valor_unidad)

    # --- Otros conceptos: monto viene desde el formulario ---
    if monto <= 0:
        flash("El monto debe ser mayor a 0.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    # Validación "de negocio": el trabajador debe haber tenido contrato vigente (solape) en el mes del lote, dentro del CC
    t = Trabajador.query.get_or_404(trabajador_id)

    inicio, siguiente = _period_bounds(lote.anio, lote.mes)

    # contrato: si viene, lo validamos; si no, lo sugerimos por solape + CC
    c: Contrato | None = None
    if contrato_id:
        c = Contrato.query.get(contrato_id)

        # Validar que el contrato corresponde al trabajador, al CC, y solapa el periodo
        if not c or getattr(c, "trabajador_id", None) != t.id:
            flash("Contrato inválido para el trabajador seleccionado.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        obra_c = getattr(c, "obra", None)
        cc_c = (getattr(obra_c, "centro_costo", "") or "").strip().upper() if obra_c else ""
        if cc_c != (lote.centro_costo or "").strip().upper():
            flash("El contrato seleccionado no pertenece al centro de costo del lote.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        if not _contrato_solapa_periodo(c, inicio, siguiente):
            flash("El contrato seleccionado no estuvo vigente durante el periodo del lote.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    if c is None:
        c = _sugerir_contrato_para_item(t.id, lote.centro_costo, lote.anio, lote.mes)

    if c is None:
        flash("No se encontró un contrato vigente en el periodo del lote para este trabajador (en este centro de costo).", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    concepto_tipo, concepto_codigo = _map_concepto_ui_a_tipo_y_codigo(concepto_ui)

    # Si es BONO, usamos código interno (obligatorio)
    if concepto_ui == "BONO":
        if not codigo_interno:
            flash("Debes seleccionar un código interno para el BONO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))
        concepto_codigo = codigo_interno

    item = ExtraRemuItem(
        lote_id=lote.id,
        trabajador_id=t.id,
        contrato_id=getattr(c, "id", None),
        obra_id=getattr(getattr(c, "obra", None), "id", None),
        empleador_id=getattr(getattr(c, "empleador", None), "id", None),
        centro_costo=lote.centro_costo,

        concepto_tipo=concepto_tipo,
        concepto_codigo=concepto_codigo,

        monto=monto,
        unidades=(unidades if concepto_ui == "TRATO" else None),
        valor_unidad=(valor_unidad if concepto_ui == "TRATO" else None),

        imponible=imponible,
        tributable=True,

        requiere_anexo=_requiere_anexo_default(concepto_ui),
        resena=resena,

        formato=formato,
        estado="BORRADOR",
        estado_doc="PENDIENTE",

        creado_por_user_id=getattr(current_user, "id", None),
    )

    db.session.add(item)
    db.session.commit()

    flash("Extra agregado.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))


@bp.post("/item/<int:item_id>/eliminar")
@login_required
def eliminar_item(item_id: int):
    item = ExtraRemuItem.query.get_or_404(item_id)
    lote = item.lote
    _assert_access_cc(lote.centro_costo)

    if lote.estado in {"CERRADO", "EXPORTADO"}:
        flash("El lote está cerrado/exportado. No se puede modificar.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    db.session.delete(item)
    db.session.commit()
    flash("Extra eliminado.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

@bp.post("/item/<int:item_id>/editar")
@login_required
def editar_item(item_id: int):
    item = ExtraRemuItem.query.get_or_404(item_id)
    lote = item.lote
    _assert_access_cc(lote.centro_costo)

    if lote.estado in {"CERRADO", "EXPORTADO"}:
        flash("El lote está cerrado/exportado. No se puede modificar.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    concepto_tipo = (item.concepto_tipo or "").strip().upper()

    # Base (para NO-TRATO el monto viene del form; para TRATO lo recalculamos)
    monto_form = _to_decimal(request.form.get("monto"))
    resena = (request.form.get("resena") or "").strip()
    imponible = (request.form.get("imponible") or "1").strip() == "1"
    formato = (request.form.get("formato") or "AMBOS").strip().upper()

    if not resena or len(resena) < 10:
        flash("Debes indicar una reseña (mínimo 10 caracteres).", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    if formato not in {"DOCX", "PDF", "AMBOS"}:
        formato = "AMBOS"

    # Cambios sensibles: detectamos si algo cambió para invalidar docs
    cambios_sensibles = False

    # --- BONO: puede cambiar código interno ---
    if concepto_tipo == "BONO":
        codigo_bono = (request.form.get("codigo_bono") or "").strip()
        if not codigo_bono:
            flash("Debes seleccionar un código interno para el BONO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        if (item.concepto_codigo or "").strip() != codigo_bono:
            cambios_sensibles = True
        item.concepto_codigo = codigo_bono

    # --- TRATO: Opción B (unidades + valor_unidad => monto calculado) ---
    if concepto_tipo == "TRATO":
        unidades = _to_decimal(request.form.get("unidades"))
        valor_unidad = _to_decimal(request.form.get("valor_unidad"))

        if unidades <= 0:
            flash("Debes indicar unidades (> 0) para TRATO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        if valor_unidad <= 0:
            flash("Debes indicar valor por unidad (> 0) para TRATO.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        nuevo_monto = _calc_monto_trato(unidades, valor_unidad)

        if (item.unidades or Decimal("0")) != unidades:
            cambios_sensibles = True
        if (item.valor_unidad or Decimal("0")) != valor_unidad:
            cambios_sensibles = True
        if (item.monto or Decimal("0")) != nuevo_monto:
            cambios_sensibles = True

        item.unidades = unidades
        item.valor_unidad = valor_unidad
        monto_final = nuevo_monto

    else:
        # NO-TRATO: monto directo del form
        if monto_form <= 0:
            flash("El monto debe ser mayor a 0.", "warning")
            return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

        if (item.monto or Decimal("0")) != monto_form:
            cambios_sensibles = True
        monto_final = monto_form

        # Si NO es TRATO, limpiamos campos de trato (higiene)
        if item.unidades is not None or item.valor_unidad is not None:
            cambios_sensibles = True
        item.unidades = None
        item.valor_unidad = None

    # Base: cambios
    if (item.resena or "").strip() != resena:
        cambios_sensibles = True
    if bool(item.imponible) != bool(imponible):
        cambios_sensibles = True
    if (item.formato or "").strip().upper() != formato:
        cambios_sensibles = True

    # Guardamos
    item.monto = monto_final
    item.resena = resena
    item.imponible = imponible
    item.formato = formato

    # Si hubo cambios sensibles: invalidar docs
    if cambios_sensibles:
        item.estado_doc = "PENDIENTE"
        item.docx_ruta = None
        item.pdf_ruta = None
        item.docx_nombre = None
        item.pdf_nombre = None
        item.estado = "BORRADOR"

    db.session.commit()
    flash("Extra actualizado.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

@bp.post("/<int:lote_id>/cambiar-estado")
@login_required
def cambiar_estado(lote_id: int):
    lote = ExtraRemuLote.query.get_or_404(lote_id)
    _assert_access_cc(lote.centro_costo)

    nuevo = (request.form.get("estado") or "").strip().upper()
    if nuevo not in {"BORRADOR", "ENVIADO", "APROBADO", "CERRADO"}:
        flash("Estado inválido.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    if lote.estado in {"EXPORTADO"}:
        flash("El lote ya fue exportado. No se puede cambiar el estado.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    lote.estado = nuevo
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))


@bp.post("/item/<int:item_id>/generar-docs")
@login_required
def generar_docs(item_id: int):
    item = ExtraRemuItem.query.get_or_404(item_id)
    lote = item.lote
    _assert_access_cc(lote.centro_costo)

    if not item.requiere_anexo:
        flash("Este ítem no requiere anexo.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))

    docx_tmp, docx_nombre, pdf_tmp, pdf_nombre, docx_guardado, pdf_guardado = generar_docx_y_pdf_extra_item(item)

    item.docx_nombre = docx_nombre
    item.docx_ruta = docx_guardado or docx_tmp

    item.pdf_nombre = pdf_nombre
    item.pdf_ruta = pdf_guardado or pdf_tmp

    _set_estado_doc_por_formato(item)

    item.estado = "EMITIDO_DOCS"

    db.session.commit()
    flash("Documentos generados.", "success")
    return redirect(url_for("extras_remuneracion.detalle", lote_id=lote.id))


@bp.get("/item/<int:item_id>/descargar-docx")
@login_required
def descargar_docx(item_id: int):
    item = ExtraRemuItem.query.get_or_404(item_id)
    lote = item.lote
    _assert_access_cc(lote.centro_costo)

    if not item.docx_ruta:
        flash("Este ítem aún no tiene DOCX generado.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=item.lote_id))

    return send_file(
        item.docx_ruta,
        as_attachment=True,
        download_name=item.docx_nombre or f"ANEXO_EXTRA_{item.id}.docx",
    )


@bp.get("/item/<int:item_id>/descargar-pdf")
@login_required
def descargar_pdf(item_id: int):
    item = ExtraRemuItem.query.get_or_404(item_id)
    lote = item.lote
    _assert_access_cc(lote.centro_costo)

    if not item.pdf_ruta:
        flash("Este ítem aún no tiene PDF generado.", "warning")
        return redirect(url_for("extras_remuneracion.detalle", lote_id=item.lote_id))

    return send_file(
        item.pdf_ruta,
        as_attachment=True,
        download_name=item.pdf_nombre or f"ANEXO_EXTRA_{item.id}.pdf",
    )


@bp.get("/<int:lote_id>/exportar-csv")
@login_required
def exportar_csv(lote_id: int):
    lote = ExtraRemuLote.query.get_or_404(lote_id)
    _assert_access_cc(lote.centro_costo)

    file_path, file_name, mimetype = export_csv_lote(lote)

    if lote.estado == "CERRADO":
        lote.estado = "EXPORTADO"
        db.session.commit()

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_name,
        mimetype=mimetype,
    )