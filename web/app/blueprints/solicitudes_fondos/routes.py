# web/app/blueprints/solicitudes_fondos/routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List
from collections import defaultdict
from io import BytesIO
import time

import re
import uuid

import sqlalchemy as sa
from flask import (
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
    jsonify,
)
from flask_login import current_user, login_required
from jinja2 import TemplateError
from sqlalchemy.orm import selectinload, joinedload

from ...auth.decorators import role_required
from ...extensions import db
from ...models import (
    Obra,
    RendicionGasto,
    SolicitudFondos,
    SolicitudFondosItem,
    SueldoDetalle,
    SueldoNomina,
    AnticipoDetalle,
    AnticipoNomina,
    Tercero,
    Trabajador,
    User,
    Empleador,
    SolicitudFondosNominaBanco,
    SolicitudFondosNominaBancoDetalle
)

from ...services.bank_nominas import (
    TEMPLATE_PAGOS_PROV,
    ProveedorRow,
    build_proveedor_rows_from_sf_items,
    build_xlsx_from_template,
    get_template_path,
)

from ...services.solicitudes_fondos_nominas_banco import (
    collect_nomina_candidates,
    create_nomina_from_candidates,
    build_xlsx_from_nomina,
)

from . import bp


SECCIONES = [
    ("REMU", "Remuneraciones"),
    ("REND", "Rendiciones de gastos"),
    ("TERC", "Contratistas y Proveedores"),
    ("VAR", "Pagos varios"),
]

ESTADOS = ["BORRADOR", "ENVIADA", "APROBADA", "RECHAZADA", "PAGADA"]

ESTADO_LABELS = {
    "BORRADOR": "Borrador",
    "ENVIADA": "Enviada a revisión",
    "APROBADA": "Aprobada",
    "RECHAZADA": "Rechazada",
    "PAGADA": "Pagada",
}

ESTADO_TRANSICIONES = {
    "BORRADOR": ["ENVIADA", "APROBADA", "RECHAZADA"],
    "ENVIADA": ["APROBADA", "RECHAZADA", "BORRADOR"],
    "APROBADA": ["PAGADA", "RECHAZADA"],
    "RECHAZADA": ["BORRADOR"],
    "PAGADA": [],
}
PERIODOS = [("QUINCENA", "Quincena"), ("FIN_MES", "Fin de mes"), ("OTRO", "Otro")]

# ============================================================
# Nóminas banco (SF) - cache simple por token (memoria del proceso)
# ============================================================
_SF_NOMINAS_CACHE: dict[str, bytes] = {}


# ---------------------------
# Accesos (scope = Centro de Costo)
# ---------------------------
def _obras_accesibles() -> List[Obra]:
    q = Obra.query
    if current_user.has_role("ADMIN"):
        return q.order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc()).all()

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return []
    return (
        q.filter(Obra.id.in_(obra_ids))
        .order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc())
        .all()
    )


def _centros_costos_accesibles() -> List[str]:
    obras = _obras_accesibles()
    ccs = sorted({(o.centro_costo or "").strip() for o in obras if (o.centro_costo or "").strip()})
    return ccs


def _assert_access_cc(centro_costo: str) -> None:
    if current_user.has_role("ADMIN"):
        return
    cc = (centro_costo or "").strip()
    if not cc or cc not in _centros_costos_accesibles():
        abort(403)


def _require_solicitud_access(s: SolicitudFondos) -> None:
    """Alias explícito para consistencia semántica en rutas de impresión."""
    _assert_access_cc(getattr(s, "centro_costo", None) or "")


# ---------------------------
# Helpers negocio
# ---------------------------
def _next_numero_por_cc(centro_costo: str) -> int:
    """Retorna el siguiente correlativo disponible para un Centro de Costo.

    La numeración de Solicitudes de Fondos es correlativa por Centro de Costo,
    respaldada además por la restricción única (centro_costo, numero) en BD.
    """
    cc = (centro_costo or "").strip()
    if not cc:
        return 1

    max_num = (
        db.session.query(sa.func.max(SolicitudFondos.numero))
        .filter(SolicitudFondos.centro_costo == cc)
        .scalar()
    )
    return int(max_num or 0) + 1


def _totales_por_seccion(items: List[SolicitudFondosItem]) -> Dict[str, Decimal]:
    tot: Dict[str, Decimal] = {k: Decimal("0.00") for k, _ in SECCIONES}
    for it in items:
        key = (getattr(it, "seccion", None) or "").strip().upper()
        if not key:
            continue
        if key not in tot:
            tot[key] = Decimal("0.00")
        tot[key] = tot.get(key, Decimal("0.00")) + (it.monto or Decimal("0.00"))
    return tot


def _estado_transiciones_permitidas(estado: str | None, is_admin: bool = False) -> list[str]:
    actual = (estado or "").strip().upper()
    permitidos = list(ESTADO_TRANSICIONES.get(actual, []))

    # Rescate administrativo acotado: permite corregir una SF aprobada sin abrir la puerta a PAGADA.
    if is_admin and actual == "APROBADA" and "BORRADOR" not in permitidos:
        permitidos.append("BORRADOR")

    return permitidos


def _estado_label(estado: str | None) -> str:
    e = (estado or "").strip().upper()
    return ESTADO_LABELS.get(e, e.title() if e else "-")


def _estado_transiciones_permitidas(estado: str | None, is_admin: bool = False) -> list[str]:
    actual = (estado or "").strip().upper()
    permitidos = list(ESTADO_TRANSICIONES.get(actual, []))

    # Rescate administrativo acotado: permite corregir una SF aprobada.
    if is_admin and actual == "APROBADA" and "BORRADOR" not in permitidos:
        permitidos.append("BORRADOR")

    return permitidos


def _estado_label(estado: str | None) -> str:
    e = (estado or "").strip().upper()
    return ESTADO_LABELS.get(e, e.title() if e else "-")


def _sf_bitacora_ensure_table() -> None:
    """Crea la tabla de bitácora si aún no existe. Evita migración Alembic para este parche operativo."""
    db.session.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS solicitudes_fondos_bitacora (
            id SERIAL PRIMARY KEY,
            solicitud_id INTEGER NOT NULL REFERENCES solicitudes_fondos(id) ON DELETE CASCADE,
            accion VARCHAR(60) NOT NULL,
            estado_anterior VARCHAR(20),
            estado_nuevo VARCHAR(20),
            detalle TEXT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    db.session.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_sf_bitacora_solicitud_fecha
        ON solicitudes_fondos_bitacora (solicitud_id, creado_en DESC)
    """))


def _sf_registrar_movimiento(
    solicitud: SolicitudFondos,
    accion: str,
    detalle: str | None = None,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
) -> None:
    try:
        _sf_bitacora_ensure_table()
        db.session.execute(
            sa.text("""
                INSERT INTO solicitudes_fondos_bitacora
                    (solicitud_id, accion, estado_anterior, estado_nuevo, detalle, user_id)
                VALUES
                    (:solicitud_id, :accion, :estado_anterior, :estado_nuevo, :detalle, :user_id)
            """),
            {
                "solicitud_id": int(solicitud.id),
                "accion": (accion or "MOVIMIENTO")[:60],
                "estado_anterior": estado_anterior,
                "estado_nuevo": estado_nuevo,
                "detalle": detalle,
                "user_id": getattr(current_user, "id", None),
            },
        )
    except Exception as exc:
        # La operación principal no debe caerse por una bitácora; se deja rastro en logs.
        try:
            current_app.logger.warning("No se pudo registrar bitácora SF %s: %s", getattr(solicitud, "id", None), exc)
        except Exception:
            pass


def _sf_get_bitacora(solicitud_id: int) -> list[dict]:
    try:
        _sf_bitacora_ensure_table()
        rows = db.session.execute(
            sa.text("""
                SELECT
                    b.id,
                    b.accion,
                    b.estado_anterior,
                    b.estado_nuevo,
                    b.detalle,
                    b.creado_en,
                    COALESCE(u.nombre, u.username, u.email, 'Usuario sistema') AS usuario_nombre
                FROM solicitudes_fondos_bitacora b
                LEFT JOIN users u ON u.id = b.user_id
                WHERE b.solicitud_id = :sid
                ORDER BY b.creado_en DESC, b.id DESC
                LIMIT 80
            """),
            {"sid": int(solicitud_id)},
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _badge_class_estado(estado: str | None) -> str:
    e = (estado or "").strip().upper()
    mapping = {
        "BORRADOR":  "cs-badge cs-badge-muted",
        "PENDIENTE": "cs-badge cs-badge-warning",
        "ENVIADA":   "cs-badge cs-badge-warning",
        "APROBADA":  "cs-badge cs-badge-success",
        "PAGADA":    "cs-badge cs-badge-success",
        "RECHAZADA": "cs-badge cs-badge-danger",
        "ANULADA":   "cs-badge cs-badge-danger",
    }
    return mapping.get(e, "cs-badge cs-badge-muted")


def _to_decimal_money(v) -> Decimal:
    """
    Convierte valores tipo dinero a Decimal("0.00") de forma tolerante.
    Acepta: Decimal, int/float, "$ 1.234.567", "1,23", "1.234,56", etc.
    """
    try:
        if v is None:
            return Decimal("0.00")
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))

        s = str(v).strip()
        if not s:
            return Decimal("0.00")

        s = s.replace("$", "").replace(" ", "")

        has_dot = "." in s
        has_comma = "," in s

        # 1.234,56
        if has_dot and has_comma:
            s = s.replace(".", "").replace(",", ".")
            return Decimal(s)

        # 1234,56
        if has_comma and not has_dot:
            s = s.replace(",", ".")
            return Decimal(s)

        # 1.234.567 o 1234.56 (ambiguo)
        if has_dot and not has_comma:
            parts = s.split(".")
            if len(parts) >= 3:
                s = "".join(parts)
                return Decimal(s)

            left, right = s.split(".", 1)
            if right.isdigit() and len(right) == 3 and left.isdigit():
                s = s.replace(".", "")
                return Decimal(s)

            return Decimal(s)

        return Decimal(s)
    except Exception:
        return Decimal("0.00")


def _assert_editable_solicitud(s: SolicitudFondos) -> bool:
    if (s.estado or "").upper().strip() != "BORRADOR":
        flash("La solicitud no es editable porque su estado no es BORRADOR.", "warning")
        return False
    return True


def _is_seccion_bloqueada_manual(seccion: str) -> bool:
    s = (seccion or "").upper().strip()
    return s in ("REMU", "REND")


def _build_items_by_seccion(items: List[SolicitudFondosItem]) -> Dict[str, List[SolicitudFondosItem]]:
    out: Dict[str, List[SolicitudFondosItem]] = {k: [] for k, _ in SECCIONES}
    for it in items:
        key = (getattr(it, "seccion", None) or "").strip().upper()
        if key in out:
            out[key].append(it)
    return out

def _parse_periodo_ym(periodo: str) -> tuple[int, int] | tuple[None, None]:
    m = re.fullmatch(r"(\d{4})-(\d{2})", (periodo or "").strip())
    if not m:
        return (None, None)
    anio = int(m.group(1))
    mes = int(m.group(2))
    if mes < 1 or mes > 12:
        return (None, None)
    return (anio, mes)


def _fmt_clp_text(v) -> str:
    try:
        n = _to_decimal_money(v)
        return "{:,.0f}".format(float(n)).replace(",", ".")
    except Exception:
        return "0"

class SimplePagination:
    def __init__(self, page: int, per_page: int, total: int):
        self.page = page
        self.per_page = per_page
        self.total = total

    @property
    def pages(self) -> int:
        if self.total <= 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int:
        return self.page - 1

    @property
    def next_num(self) -> int:
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=2, right_edge=2):
        last = 0
        total_pages = self.pages

        for num in range(1, total_pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > total_pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num

# ============================================================
# Listado
# ============================================================
@bp.get("/")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    centros_costos = _centros_costos_accesibles()

    cc = (request.args.get("centro_costo") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    desde = request.args.get("desde") or ""
    hasta = request.args.get("hasta") or ""
    page = request.args.get("page", 1, type=int)
    per_page = 30

    # ------------------------------------------------------------
    # Query base SOLO para filtros / count / IDs paginados
    # ------------------------------------------------------------
    q_base = SolicitudFondos.query

    if not current_user.has_role("ADMIN"):
        if not centros_costos:
            q_base = q_base.filter(sa.text("1=0"))
        else:
            q_base = q_base.filter(SolicitudFondos.centro_costo.in_(centros_costos))

    if cc:
        _assert_access_cc(cc)
        q_base = q_base.filter(SolicitudFondos.centro_costo == cc)

    if estado in ESTADOS:
        q_base = q_base.filter(SolicitudFondos.estado == estado)

    try:
        if desde:
            d = datetime.strptime(desde, "%Y-%m-%d").date()
            q_base = q_base.filter(SolicitudFondos.fecha_solicitud >= d)
        if hasta:
            h = datetime.strptime(hasta, "%Y-%m-%d").date()
            q_base = q_base.filter(SolicitudFondos.fecha_solicitud <= h)
    except ValueError:
        flash("Rango de fechas inválido.", "warning")

    # ------------------------------------------------------------
    # Paginación manual liviana
    # ------------------------------------------------------------
    total = q_base.order_by(None).count()

    offset = max(page - 1, 0) * per_page

    ids_rows = (
        q_base.with_entities(SolicitudFondos.id)
        .order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    sol_ids = [int(r[0]) for r in ids_rows if r and r[0]]

    # ------------------------------------------------------------
    # Query plana con SOLO las columnas necesarias para el listado
    # ------------------------------------------------------------
    solicitudes = []

    if sol_ids:
        rows = (
            db.session.query(
                SolicitudFondos.id,
                SolicitudFondos.numero,
                SolicitudFondos.centro_costo,
                SolicitudFondos.fecha_solicitud,
                SolicitudFondos.periodo_tipo,
                SolicitudFondos.estado,
                SolicitudFondos.obra_id,
                Obra.codigo.label("obra_codigo"),
                Obra.nombre.label("obra_nombre"),
            )
            .outerjoin(Obra, SolicitudFondos.obra_id == Obra.id)
            .filter(SolicitudFondos.id.in_(sol_ids))
            .all()
        )

        rows_map = {int(r.id): r for r in rows}
        solicitudes = [rows_map[sid] for sid in sol_ids if sid in rows_map]

    pagination = SimplePagination(page=page, per_page=per_page, total=total)

    # ============================================================
    # Totales rápidos SOLO para la página actual
    # ============================================================
    tot_map: dict[int, dict[str, Decimal]] = {}

    for sid in sol_ids:
        tot_map[sid] = {
            "REMU": Decimal("0.00"),
            "REND": Decimal("0.00"),
            "TERC": Decimal("0.00"),
            "VAR": Decimal("0.00"),
            "TOTAL": Decimal("0.00"),
        }

    if sol_ids:
        rows_items = (
            db.session.query(
                SolicitudFondosItem.solicitud_id,
                SolicitudFondosItem.seccion,
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0),
            )
            .filter(SolicitudFondosItem.solicitud_id.in_(sol_ids))
            .group_by(SolicitudFondosItem.solicitud_id, SolicitudFondosItem.seccion)
            .all()
        )

        for sid, seccion, total_sec in rows_items:
            sid_i = int(sid)
            key = (seccion or "").strip().upper()
            if sid_i in tot_map and key in tot_map[sid_i]:
                tot_map[sid_i][key] = _to_decimal_money(total_sec)

        try:
            rendiciones = (
                RendicionGasto.query
                .filter(RendicionGasto.solicitud_fondos_id.in_(sol_ids))
                .options(selectinload(RendicionGasto.items))
                .all()
            )

            for r in rendiciones:
                sid = getattr(r, "solicitud_fondos_id", None)
                if not sid or sid not in tot_map:
                    continue

                r_items = getattr(r, "items", None) or []
                r_total = sum([(it.monto or Decimal("0.00")) for it in r_items], Decimal("0.00"))
                tot_map[sid]["REND"] += _to_decimal_money(r_total)

        except Exception:
            pass

        for sid in sol_ids:
            d = tot_map[sid]
            d["TOTAL"] = d["REMU"] + d["REND"] + d["TERC"] + d["VAR"]

    return render_template(
        "solicitudes_fondos/listado.html",
        centros_costos=centros_costos,
        solicitudes=solicitudes,
        pagination=pagination,
        centro_costo=cc,
        estado=estado,
        desde=desde,
        hasta=hasta,
        estados=ESTADOS,
        badge_estado=_badge_class_estado,
        tot_map=tot_map,
    )



@bp.get("/api/siguiente-numero")
@login_required
@role_required("ADMIN", "OPERADOR")
def api_siguiente_numero():
    """Entrega el siguiente N° de Solicitud de Fondos para el Centro de Costo seleccionado."""
    cc = (request.args.get("centro_costo") or "").strip()
    if not cc:
        return jsonify({"ok": False, "message": "Debes seleccionar un Centro de Costo."}), 400

    _assert_access_cc(cc)
    return jsonify({
        "ok": True,
        "centro_costo": cc,
        "siguiente_numero": _next_numero_por_cc(cc),
    })

# ============================================================
# Nueva
# ============================================================
@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("ADMIN", "OPERADOR")
def nueva():
    centros_costos = _centros_costos_accesibles()
    obras = _obras_accesibles()

    if not centros_costos and not current_user.has_role("ADMIN"):
        flash("No tienes centros de costo disponibles (no hay obras asignadas).", "warning")
        return redirect(url_for("solicitudes_fondos.listado"))

    if request.method == "POST":
        cc = (request.form.get("centro_costo") or "").strip()
        if not cc:
            flash("Debes seleccionar un Centro de Costo.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        _assert_access_cc(cc)

        obra_id = request.form.get("obra_id", type=int)
        if obra_id:
            obra = Obra.query.get(obra_id)
            if not obra or (obra.centro_costo or "").strip() != cc:
                flash("Obra de referencia inválida para el Centro de Costo seleccionado.", "warning")
                return redirect(url_for("solicitudes_fondos.nueva"))

        # El correlativo se calcula en backend según el Centro de Costo seleccionado.
        # No dependemos del valor visual del formulario para evitar duplicidades manuales.
        numero = _next_numero_por_cc(cc)
        fecha_solicitud_str = request.form.get("fecha_solicitud") or ""
        periodo_tipo = (request.form.get("periodo_tipo") or "").strip().upper()
        periodo_desde_str = request.form.get("periodo_desde") or ""
        periodo_hasta_str = request.form.get("periodo_hasta") or ""
        observaciones = (request.form.get("observaciones") or "").strip() or None

        try:
            fecha_solicitud = datetime.strptime(fecha_solicitud_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Fecha de solicitud inválida.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        if periodo_tipo not in dict(PERIODOS):
            flash("Tipo de período inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))

        periodo_desde = None
        periodo_hasta = None
        try:
            if periodo_desde_str:
                periodo_desde = datetime.strptime(periodo_desde_str, "%Y-%m-%d").date()
            if periodo_hasta_str:
                periodo_hasta = datetime.strptime(periodo_hasta_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Período desde/hasta inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.nueva"))


        s = SolicitudFondos(
            centro_costo=cc,
            obra_id=obra_id or None,
            numero=numero,
            fecha_solicitud=fecha_solicitud,
            periodo_tipo=periodo_tipo,
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
            estado="BORRADOR",
            observaciones=observaciones,
            creado_por_user_id=current_user.id,
        )
        db.session.add(s)
        try:
            db.session.commit()
            _sf_registrar_movimiento(
                s,
                "CREACION_SOLICITUD",
                f"Solicitud creada en BORRADOR para el Centro de Costo {cc}.",
                estado_anterior=None,
                estado_nuevo="BORRADOR",
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("No se pudo crear la solicitud (¿número duplicado para el Centro de Costo?).", "danger")
            return redirect(url_for("solicitudes_fondos.nueva"))

        flash("Solicitud creada en estado BORRADOR.", "success")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    return render_template(
        "solicitudes_fondos/nueva.html",
        centros_costos=centros_costos,
        obras=obras,
        periodos=PERIODOS,
        hoy=date.today().strftime("%Y-%m-%d"),
    )


# ============================================================
# Detalle
# ============================================================
@bp.get("/<int:solicitud_id>")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    solo_lectura = current_user.has_role("REVISOR") or ((s.estado or "").upper().strip() != "BORRADOR")

    items = list(s.items or [])
    tot = _totales_por_seccion(items)

    obras_cc = (
        Obra.query.filter(Obra.centro_costo == s.centro_costo)
        .order_by(Obra.nombre.asc())
        .all()
    )

    # ------------------------------------------------------------
    # ⚡ Optimización:
    # Solo cargar terceros / trabajadores cuando realmente se usarán
    # (formularios de edición/agregado).
    # ------------------------------------------------------------
    terceros = []
    trabajadores = []

    if not solo_lectura:
        terceros = (
            Tercero.query.filter(Tercero.estado == "VIGENTE")
            .order_by(Tercero.ap_paterno.asc())
            .limit(500)
            .all()
        )

        trabajadores = (
            Trabajador.query
            .order_by(
                sa.case((Trabajador.estado_trabajador == "VIGENTE", 0), else_=1).asc(),
                Trabajador.ap_paterno.asc(),
                Trabajador.ap_materno.asc().nullslast(),
                Trabajador.nombres.asc(),
            )
            .limit(800)
            .all()
        )

    # ============================================================
    # REMU: resumen anticipos (QUINCENA) desde service "anticipos_reader"
    # ============================================================
    resumen_anticipos = None
    if (s.periodo_tipo or "").upper().strip() == "QUINCENA":
        ref_date = s.periodo_desde or s.fecha_solicitud
        try:
            from ...services.anticipos_reader import get_resumen_anticipos_para_quincena  # noqa

            resumen_anticipos = get_resumen_anticipos_para_quincena(
                centro_costo=(s.centro_costo or "").strip(),
                anio=int(ref_date.year),
                mes=int(ref_date.month),
            )
        except Exception:
            resumen_anticipos = None

    if resumen_anticipos:
        remu_total = _to_decimal_money(getattr(resumen_anticipos, "total_monto", None))
        tot["REMU"] = remu_total

    # ============================================================
    # REMU (QUINCENA): Cards desde ANTICIPOS integrados a la SF
    # ============================================================
    remu_anticipos_cards: List[dict] = []

    def _tipo_key(tipo: str | None) -> str:
        t = (tipo or "SIN TIPO")
        return str(t).strip().upper() or "SIN TIPO"

    def _tipo_sort_key(tipo: str | None):
        key = _tipo_key(tipo)
        prio = 0 if key in ("JEFATURA U OTROS", "JEFATURA Y OTROS") else 1
        return (prio, key)

    try:
        items_remu_anticipos = (
            SolicitudFondosItem.query
            .filter(
                SolicitudFondosItem.solicitud_id == s.id,
                SolicitudFondosItem.seccion == "REMU",
                SolicitudFondosItem.anticipo_detalle_id.isnot(None),
            )
            .options(
                joinedload(SolicitudFondosItem.anticipo_nomina),
                joinedload(SolicitudFondosItem.anticipo_detalle).joinedload(AnticipoDetalle.trabajador),
            )
            .order_by(SolicitudFondosItem.id.asc())
            .all()
        )

        by_nomina: dict[int, dict] = {}

        for it in items_remu_anticipos:
            nom = getattr(it, "anticipo_nomina", None)
            det = getattr(it, "anticipo_detalle", None)
            if not nom or not det:
                continue

            nid = int(getattr(nom, "id", 0) or 0)
            if not nid:
                continue

            if nid not in by_nomina:
                by_nomina[nid] = {
                    "nomina": nom,
                    "por_tipo_monto": defaultdict(Decimal),
                    "por_tipo_ids": defaultdict(set),
                    "total": Decimal("0.00"),
                }

            t = getattr(det, "trabajador", None)
            tipo_raw = getattr(t, "tipo_trabajador", None) if t else None
            tipo = (tipo_raw or "SIN TIPO").strip() if isinstance(tipo_raw, str) else (tipo_raw or "SIN TIPO")

            monto = _to_decimal_money(getattr(det, "monto", None))

            by_nomina[nid]["por_tipo_monto"][tipo] += monto
            by_nomina[nid]["total"] += monto

            tid = getattr(t, "id", None) if t else None
            if tid:
                by_nomina[nid]["por_tipo_ids"][tipo].add(int(tid))

        for data in by_nomina.values():
            por_tipo_list = []
            for tipo, total_tipo in data["por_tipo_monto"].items():
                cant = len(data["por_tipo_ids"].get(tipo, set()))
                por_tipo_list.append((tipo, total_tipo, cant))

            por_tipo_list.sort(key=lambda x: _tipo_sort_key(x[0]))

            remu_anticipos_cards.append(
                {
                    "nomina": data["nomina"],
                    "subtotales_tipo": por_tipo_list,
                    "total": data["total"],
                }
            )

        remu_anticipos_cards.sort(
            key=lambda x: (
                int(getattr(x["nomina"], "anio", 0) or 0),
                int(getattr(x["nomina"], "mes", 0) or 0),
                int(getattr(x["nomina"], "id", 0) or 0),
            )
        )

        if (not resumen_anticipos) and remu_anticipos_cards:
            tot["REMU"] = sum([c["total"] for c in remu_anticipos_cards], Decimal("0.00"))

    except Exception:
        remu_anticipos_cards = []

    # ============================================================
    # REMU (QUINCENA): fallback si no hay resumen service y no hay cards por anticipo_nomina
    # ============================================================
    if (not resumen_anticipos) and (not remu_anticipos_cards):
        try:
            items_remu = (
                SolicitudFondosItem.query
                .filter(
                    SolicitudFondosItem.solicitud_id == s.id,
                    SolicitudFondosItem.seccion == "REMU",
                    SolicitudFondosItem.anticipo_detalle_id.isnot(None),
                )
                .options(joinedload(SolicitudFondosItem.trabajador))
                .all()
            )

            if items_remu:
                subt_monto = defaultdict(Decimal)
                subt_ids = defaultdict(set)
                total = Decimal("0.00")

                for it in items_remu:
                    tr = getattr(it, "trabajador", None)

                    if tr:
                        tipo_raw = getattr(tr, "tipo_trabajador", None)
                        tipo = (str(tipo_raw).strip() if tipo_raw else "SIN TIPO") or "SIN TIPO"
                        tid = getattr(tr, "id", None)
                        if tid:
                            subt_ids[tipo].add(int(tid))
                    else:
                        tipo = "JEFATURA U OTROS"

                    monto = _to_decimal_money(getattr(it, "monto", None))
                    subt_monto[tipo] += monto
                    total += monto

                subt_list = []
                for tipo, monto_tipo in subt_monto.items():
                    cant = len(subt_ids.get(tipo, set()))
                    subt_list.append((tipo, monto_tipo, cant))

                subt_list.sort(key=lambda x: _tipo_sort_key(x[0]))

                remu_anticipos_cards = [
                    {
                        "nomina": None,
                        "subtotales_tipo": subt_list,
                        "total": total,
                    }
                ]
                tot["REMU"] = total
        except Exception:
            pass

    # ============================================================
    # REMU (FIN_MES): Cards desde SUELDOS integrados
    # ============================================================
    remu_sueldos_cards: List[dict] = []
    is_fin_mes = (s.periodo_tipo or "").upper().strip() == "FIN_MES"

    if is_fin_mes:
        try:
            items_remu_sueldos = (
                SolicitudFondosItem.query
                .filter(
                    SolicitudFondosItem.solicitud_id == s.id,
                    SolicitudFondosItem.seccion == "REMU",
                    SolicitudFondosItem.sueldo_detalle_id.isnot(None),
                )
                .options(
                    joinedload(SolicitudFondosItem.sueldo_nomina),
                    joinedload(SolicitudFondosItem.sueldo_detalle).joinedload(SueldoDetalle.trabajador),
                )
                .order_by(SolicitudFondosItem.id.asc())
                .all()
            )

            by_nomina: dict[int, dict] = {}

            for it in items_remu_sueldos:
                nom = getattr(it, "sueldo_nomina", None)
                det = getattr(it, "sueldo_detalle", None)
                if not nom or not det:
                    continue

                nid = int(getattr(nom, "id", 0) or 0)
                if not nid:
                    continue

                if nid not in by_nomina:
                    by_nomina[nid] = {
                        "nomina": nom,
                        "por_tipo_monto": defaultdict(Decimal),
                        "por_tipo_ids": defaultdict(set),
                        "total": Decimal("0.00"),
                    }

                t = getattr(det, "trabajador", None)
                tipo_raw = getattr(t, "tipo_trabajador", None) if t else None
                tipo = (tipo_raw or "SIN TIPO").strip() if isinstance(tipo_raw, str) else (tipo_raw or "SIN TIPO")

                monto = _to_decimal_money(getattr(det, "liquido", None))

                by_nomina[nid]["por_tipo_monto"][tipo] += monto
                by_nomina[nid]["total"] += monto

                tid = getattr(t, "id", None) if t else None
                if tid:
                    by_nomina[nid]["por_tipo_ids"][tipo].add(int(tid))

            for data in by_nomina.values():
                por_tipo_list = []
                for tipo, total_tipo in data["por_tipo_monto"].items():
                    cant = len(data["por_tipo_ids"].get(tipo, set()))
                    por_tipo_list.append((tipo, total_tipo, cant))

                por_tipo_list.sort(key=lambda x: _tipo_sort_key(x[0]))

                remu_sueldos_cards.append(
                    {
                        "nomina": data["nomina"],
                        "subtotales_tipo": por_tipo_list,
                        "total": data["total"],
                    }
                )

            remu_sueldos_cards.sort(
                key=lambda x: (
                    int(getattr(x["nomina"], "anio", 0) or 0),
                    int(getattr(x["nomina"], "mes", 0) or 0),
                    int(getattr(x["nomina"], "id", 0) or 0),
                )
            )

            if (not resumen_anticipos) and remu_sueldos_cards:
                tot["REMU"] = sum([c["total"] for c in remu_sueldos_cards], Decimal("0.00"))

        except Exception:
            remu_sueldos_cards = []

        # ============================================================
        # REMU (FIN_MES): fallback robusto desde ítems REMU ya integrados
        # ============================================================
        if (not resumen_anticipos) and (not remu_sueldos_cards):
            try:
                items_remu = (
                    SolicitudFondosItem.query
                    .filter(
                        SolicitudFondosItem.solicitud_id == s.id,
                        SolicitudFondosItem.seccion == "REMU",
                    )
                    .options(joinedload(SolicitudFondosItem.trabajador))
                    .all()
                )

                if items_remu:
                    subt_monto = defaultdict(Decimal)
                    subt_ids = defaultdict(set)
                    total = Decimal("0.00")

                    for it in items_remu:
                        tr = getattr(it, "trabajador", None)
                        if not tr:
                            tipo = "JEFATURA U OTROS"
                        else:
                            tipo_val = (getattr(tr, "tipo_trabajador", None) or "").strip()
                            tipo = tipo_val if tipo_val else "SIN TIPO"
                            tid = getattr(tr, "id", None)
                            if tid:
                                subt_ids[tipo].add(int(tid))

                        monto = _to_decimal_money(getattr(it, "monto", None))
                        subt_monto[tipo] += monto
                        total += monto

                    subt_list = []
                    for tipo, monto_tipo in subt_monto.items():
                        cant = len(subt_ids.get(tipo, set()))
                        subt_list.append((tipo, monto_tipo, cant))

                    subt_list.sort(key=lambda x: _tipo_sort_key(x[0]))

                    remu_sueldos_cards = [{
                        "nomina": None,
                        "subtotales_tipo": subt_list,
                        "total": total,
                    }]
                    tot["REMU"] = total
            except Exception:
                pass

    # ============================================================
    # REND: resumen rendiciones vinculadas (lo que usa el template)
    # ============================================================
    def _fmt_rut_from_user(u) -> str | None:
        if not u:
            return None
        rut_completo = getattr(u, "rut_completo", None)
        if rut_completo:
            return str(rut_completo)
        rut = getattr(u, "rut", None)
        if rut:
            return str(rut)
        rut_num = getattr(u, "rut_num", None)
        dv = getattr(u, "dv", None)
        if rut_num and dv:
            return f"{rut_num}-{dv}"
        return None

    def _nombre_usuario(u) -> str | None:
        if not u:
            return None
        nombre = getattr(u, "nombre", None) or getattr(u, "first_name", None)
        apellido = getattr(u, "apellido", None) or getattr(u, "last_name", None)
        if nombre and apellido:
            return f"{nombre} {apellido}"
        if nombre:
            return str(nombre)
        return str(getattr(u, "username", None) or getattr(u, "email", None) or getattr(u, "id", None))

    def _rendicion_fk_filter(model, solicitud_id_val: int):
        if hasattr(model, "solicitud_fondos_id"):
            return getattr(model, "solicitud_fondos_id") == solicitud_id_val
        if hasattr(model, "solicitud_id"):
            return getattr(model, "solicitud_id") == solicitud_id_val
        if hasattr(model, "solicitudfondos_id"):
            return getattr(model, "solicitudfondos_id") == solicitud_id_val
        return sa.text("1=0")

    resumen_rendiciones: List[dict] = []
    total_rendiciones = Decimal("0.00")

    try:
        opts = [selectinload(RendicionGasto.items)]
        if hasattr(RendicionGasto, "creado_por"):
            opts.append(selectinload(RendicionGasto.creado_por))
        elif hasattr(RendicionGasto, "usuario"):
            opts.append(selectinload(RendicionGasto.usuario))
        elif hasattr(RendicionGasto, "user"):
            opts.append(selectinload(RendicionGasto.user))

        rendiciones = (
            RendicionGasto.query
            .filter(_rendicion_fk_filter(RendicionGasto, s.id))
            .options(*opts)
            .order_by(RendicionGasto.id.asc())
            .all()
        )

        for r in rendiciones:
            r_items = getattr(r, "items", None) or []
            r_total = sum([(it.monto or Decimal("0.00")) for it in r_items], Decimal("0.00"))
            total_rendiciones += r_total

            u = getattr(r, "creado_por", None) or getattr(r, "usuario", None) or getattr(r, "user", None)

            resumen_rendiciones.append(
                {
                    "rendicion_id": r.id,
                    "rendicion_numero": getattr(r, "numero", None) or r.id,
                    "usuario_nombre": _nombre_usuario(u),
                    "usuario_rut": _fmt_rut_from_user(u),
                    "total": r_total,
                }
            )

        if resumen_rendiciones:
            tot["REND"] = total_rendiciones

    except Exception:
        resumen_rendiciones = []

    total_general = sum(tot.values()) if tot else Decimal("0.00")

    # ============================================================
    # Trazabilidad bancaria: líneas de nómina que pagaron esta SF
    # ============================================================
    bank_trace = []
    bank_trace_total = Decimal("0.00")
    try:
        bank_rows = (
            SolicitudFondosNominaBancoDetalle.query
            .join(SolicitudFondosNominaBanco, SolicitudFondosNominaBancoDetalle.nomina_id == SolicitudFondosNominaBanco.id)
            .filter(SolicitudFondosNominaBancoDetalle.solicitud_id == s.id)
            .order_by(SolicitudFondosNominaBanco.fecha_generacion.desc(), SolicitudFondosNominaBanco.id.desc())
            .all()
        )
        for br in bank_rows:
            bank_trace.append(br)
            bank_trace_total += _to_decimal_money(getattr(br, "monto_pagado_en_esta_nomina", None))
    except Exception:
        bank_trace = []
        bank_trace_total = Decimal("0.00")

    bitacora_rows = _sf_get_bitacora(s.id)

    return render_template(
        "solicitudes_fondos/detalle.html",
        s=s,
        obras_cc=obras_cc,
        secciones=SECCIONES,
        estados=ESTADOS,
        periodos=PERIODOS,
        badge_estado=_badge_class_estado,
        items=items,
        tot=tot,
        total_general=total_general,
        terceros=terceros,
        trabajadores=trabajadores,
        solo_lectura=solo_lectura,
        resumen_anticipos=resumen_anticipos,
        resumen_rendiciones=resumen_rendiciones,
        remu_sueldos_cards=remu_sueldos_cards,
        remu_anticipos_cards=remu_anticipos_cards,
        bitacora_rows=bitacora_rows,
        estados_permitidos=_estado_transiciones_permitidas(s.estado, current_user.has_role("ADMIN")),
        estado_labels=ESTADO_LABELS,
        bank_trace=bank_trace,
        bank_trace_total=bank_trace_total,
    )


# ============================================================
# Cambiar estado
# ============================================================
@bp.post("/<int:solicitud_id>/estado")
@login_required
@role_required("ADMIN", "OPERADOR")
def cambiar_estado(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    estado_actual = (s.estado or "").strip().upper()
    estado = (request.form.get("estado") or "").strip().upper()
    motivo_rechazo = (request.form.get("motivo_rechazo") or "").strip()

    if estado not in ESTADOS:
        flash("Estado inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if estado == estado_actual:
        flash("La solicitud ya se encuentra en ese estado.", "info")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    permitidos = _estado_transiciones_permitidas(estado_actual, current_user.has_role("ADMIN"))
    if estado not in permitidos:
        flash(f"Transición no permitida: {_estado_label(estado_actual)} → {_estado_label(estado)}.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if estado == "RECHAZADA" and not motivo_rechazo:
        flash("Debes indicar el motivo del rechazo.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    # Control interno: no enviar/aprobar solicitudes sin movimientos.
    if estado in ("ENVIADA", "APROBADA"):
        has_items = bool((s.items or []))
        has_rend = False
        try:
            has_rend = RendicionGasto.query.filter(RendicionGasto.solicitud_fondos_id == s.id).first() is not None
        except Exception:
            has_rend = False
        if not has_items and not has_rend:
            flash("No puedes enviar/aprobar una solicitud sin movimientos.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    detalle = f"Cambio de estado: {_estado_label(estado_actual)} → {_estado_label(estado)}."
    if estado == "RECHAZADA":
        detalle = f"Solicitud rechazada. Motivo: {motivo_rechazo}"
    elif estado == "BORRADOR" and estado_actual in ("RECHAZADA", "ENVIADA", "APROBADA"):
        detalle = f"Solicitud devuelta a borrador desde {_estado_label(estado_actual)} para correcciones."

    s.estado = estado
    _sf_registrar_movimiento(
        s,
        "CAMBIO_ESTADO",
        detalle,
        estado_anterior=estado_actual,
        estado_nuevo=estado,
    )
    db.session.commit()

    flash(f"Estado actualizado: {_estado_label(estado_actual)} → {_estado_label(estado)}.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if estado == estado_actual:
        flash("La solicitud ya se encuentra en ese estado.", "info")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    permitidos = _estado_transiciones_permitidas(estado_actual, current_user.has_role("ADMIN"))
    if estado not in permitidos:
        flash(f"Transición no permitida: {_estado_label(estado_actual)} → {_estado_label(estado)}.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    # Validación básica de control: no aprobar/enviar solicitudes completamente vacías.
    if estado in ("ENVIADA", "APROBADA"):
        has_items = bool((s.items or []))
        has_rend = False
        try:
            has_rend = RendicionGasto.query.filter(RendicionGasto.solicitud_fondos_id == s.id).first() is not None
        except Exception:
            has_rend = False
        if not has_items and not has_rend:
            flash("No puedes enviar/aprobar una solicitud sin movimientos.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    s.estado = estado
    db.session.commit()
    flash(f"Estado actualizado: {_estado_label(estado_actual)} → {_estado_label(estado)}.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    s.estado = estado
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))


# ============================================================
# Ítems: agregar / editar / eliminar
# ============================================================
@bp.post("/<int:solicitud_id>/items/agregar", endpoint="item_agregar")
@login_required
@role_required("ADMIN", "OPERADOR")
def item_agregar(solicitud_id: int):
    s: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    seccion = (request.form.get("seccion") or "").strip().upper()
    if seccion not in dict(SECCIONES):
        flash("Sección inválida.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if _is_seccion_bloqueada_manual(seccion):
        if seccion == "REMU":
            flash("La sección Remuneraciones se alimenta automáticamente y no admite ítems manuales.", "warning")
        else:
            flash("La sección Rendiciones se alimenta exclusivamente desde el módulo de Rendiciones de Gastos.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    enforce_registrado = seccion in ("TERC", "VAR")

    tercero_id = request.form.get("tercero_id", type=int)
    trabajador_id = request.form.get("trabajador_id", type=int)

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper() or None
    tipo_documento = (request.form.get("tipo_documento") or "").strip().upper() or None
    nro_doc_num = (request.form.get("nro_documento") or "").strip()
    concepto = (request.form.get("concepto") or "").strip().upper() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    beneficiario_nombre = (request.form.get("beneficiario_nombre") or "").strip() or None
    beneficiario_rut_num = request.form.get("beneficiario_rut_num", type=int)
    beneficiario_dv = (request.form.get("beneficiario_dv") or "").strip().upper() or None
    control_interno = (request.form.get("control_interno") or "").strip() or None

    try:
        monto = _to_decimal_money(request.form.get("monto"))
        if monto < 0:
            raise ValueError
    except Exception:
        flash("Monto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    if enforce_registrado:
        if not tercero_id and not trabajador_id:
            flash("Debes seleccionar un Tercero o un Trabajador desde la lista.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        if tercero_id and trabajador_id:
            flash("Selecciona solo un beneficiario: Tercero o Trabajador (no ambos).", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_pago = {"TRANSFERENCIA", "NOMINA_2"}
        if (tipo_pago or "") not in allowed_pago:
            flash("Tipo de pago inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_doc = {
            "FACTURA",
            "FACTURA_EXENTA",
            "BOLETA",
            "BOLETA_HONORARIOS",
            "COMPROBANTE",
            "RECIBO",
            "ORDEN_COMPRA",
            "NOTA_VENTA",
            "GUIA_DESPACHO",
            "VOUCHER",
            "LIQUIDACION",
            "CONTRATO",
            "SIN_DOCUMENTO",
        }
        if (tipo_documento or "") not in allowed_doc:
            flash("Tipo de documento inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        allowed_concepto = {
            "CONTRATISTA",
            "SERVICIOS",
            "TRATOS_INTERNOS",
            "PROVEEDORES",
            "PROVISIONES",
            "FINIQUITOS",
            "OTROS",
        }
        if (concepto or "") not in allowed_concepto:
            flash("Concepto inválido.", "warning")
            return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

        nro_documento = f"{tipo_documento}|{nro_doc_num}" if tipo_documento else None

        beneficiario_nombre = None
        beneficiario_rut_num = None
        beneficiario_dv = None
        control_interno = None
    else:
        nro_documento = (request.form.get("nro_documento") or "").strip() or None
        if not tipo_pago:
            tipo_pago = (request.form.get("tipo_pago") or "").strip() or None
        if not concepto:
            concepto = (request.form.get("concepto") or "").strip() or None

    it = SolicitudFondosItem(
        solicitud_id=solicitud_id,
        seccion=seccion,
        tercero_id=tercero_id or None,
        trabajador_id=trabajador_id or None,
        beneficiario_nombre=beneficiario_nombre,
        beneficiario_rut_num=beneficiario_rut_num,
        beneficiario_dv=beneficiario_dv,
        monto=monto,
        tipo_pago=tipo_pago,
        nro_documento=nro_documento,
        concepto=concepto,
        descripcion=descripcion,
        control_interno=control_interno,
        orden=0,
    )
    db.session.add(it)
    db.session.flush()
    _sf_registrar_movimiento(
        s,
        "ITEM_AGREGADO",
        f"Ítem agregado en sección {seccion}: {it.beneficiario_display} por $ {_fmt_clp_text(monto)}.",
        estado_anterior=s.estado,
        estado_nuevo=s.estado,
    )
    db.session.commit()

    flash("Ítem agregado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))


bp.add_url_rule(
    "/<int:solicitud_id>/items/agregar",
    endpoint="agregar_item",
    view_func=item_agregar,
    methods=["POST"],
)


@bp.post("/items/<int:item_id>/editar", endpoint="item_actualizar")
@login_required
@role_required("ADMIN", "OPERADOR")
def item_actualizar(item_id: int):
    it: SolicitudFondosItem = SolicitudFondosItem.query.get_or_404(item_id)
    s = it.solicitud
    if not s:
        abort(404)

    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    seccion = (it.seccion or "").upper().strip()
    old_monto = _to_decimal_money(getattr(it, "monto", None))
    old_beneficiario = getattr(it, "beneficiario_display", "-")

    # Solo permitimos edición modal para TERC/VAR
    if seccion not in ("TERC", "VAR"):
        flash("Este ítem no admite edición en esta pantalla (solo TERC/VAR).", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    tercero_id = request.form.get("tercero_id", type=int)
    trabajador_id = request.form.get("trabajador_id", type=int)

    if not tercero_id and not trabajador_id:
        flash("Debes seleccionar un Tercero o un Trabajador desde la lista.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    if tercero_id and trabajador_id:
        flash("Selecciona solo un beneficiario: Tercero o Trabajador (no ambos).", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper() or None
    tipo_documento = (request.form.get("tipo_documento") or "").strip().upper() or None
    nro_doc_num = (request.form.get("nro_documento") or "").strip()
    concepto = (request.form.get("concepto") or "").strip().upper() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    allowed_pago = {"TRANSFERENCIA", "NOMINA_2"}
    if (tipo_pago or "") not in allowed_pago:
        flash("Tipo de pago inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    allowed_doc = {
            "FACTURA",
            "FACTURA_EXENTA",
            "BOLETA",
            "BOLETA_HONORARIOS",
            "COMPROBANTE",
            "RECIBO",
            "ORDEN_COMPRA",
            "NOTA_VENTA",
            "GUIA_DESPACHO",
            "VOUCHER",
            "LIQUIDACION",
            "CONTRATO",
            "SIN_DOCUMENTO",
        }
    if (tipo_documento or "") not in allowed_doc:
        flash("Tipo de documento inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    allowed_concepto = {
        "CONTRATISTA",
        "SERVICIOS",
        "TRATOS_INTERNOS",
        "PROVEEDORES",
        "PROVISIONES",
        "FINIQUITOS",
        "OTROS",
    }
    if (concepto or "") not in allowed_concepto:
        flash("Concepto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    try:
        monto = _to_decimal_money(request.form.get("monto"))
        if monto < 0:
            raise ValueError
    except Exception:
        flash("Monto inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    nro_documento = f"{tipo_documento}|{nro_doc_num}" if tipo_documento else None

    it.tercero_id = tercero_id or None
    it.trabajador_id = trabajador_id or None
    it.monto = monto
    it.tipo_pago = tipo_pago
    it.nro_documento = nro_documento
    it.concepto = concepto
    it.descripcion = descripcion

    # En TERC/VAR estos deben quedar limpios
    it.beneficiario_nombre = None
    it.beneficiario_rut_num = None
    it.beneficiario_dv = None
    it.control_interno = None

    _sf_registrar_movimiento(
        s,
        "ITEM_EDITADO",
        f"Ítem editado en sección {seccion}: {old_beneficiario} por $ {_fmt_clp_text(old_monto)} → {it.beneficiario_display} por $ {_fmt_clp_text(monto)}.",
        estado_anterior=s.estado,
        estado_nuevo=s.estado,
    )
    db.session.commit()
    flash("Ítem actualizado.", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))


@bp.post("/items/<int:item_id>/eliminar", endpoint="item_eliminar")
@login_required
@role_required("ADMIN", "OPERADOR")
def item_eliminar(item_id: int):
    it: SolicitudFondosItem = SolicitudFondosItem.query.get_or_404(item_id)
    s = it.solicitud
    if not s:
        abort(404)

    _assert_access_cc(s.centro_costo)

    if not _assert_editable_solicitud(s):
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    seccion = (it.seccion or "").upper().strip()

    # 🔒 REMU y REND no se eliminan manualmente desde aquí
    if _is_seccion_bloqueada_manual(seccion):
        if seccion == "REMU":
            flash("La sección Remuneraciones se alimenta automáticamente y no admite eliminación manual.", "warning")
        else:
            flash(
                "La sección Rendiciones se alimenta desde el módulo Rendiciones de Gastos y no admite eliminación manual aquí.",
                "warning",
            )
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    detalle_eliminacion = f"Ítem eliminado en sección {seccion}: {it.beneficiario_display} por $ {_fmt_clp_text(it.monto)}."
    _sf_registrar_movimiento(
        s,
        "ITEM_ELIMINADO",
        detalle_eliminacion,
        estado_anterior=s.estado,
        estado_nuevo=s.estado,
    )
    db.session.delete(it)
    db.session.commit()
    flash("Ítem eliminado.", "info")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))


@bp.post("/<int:solicitud_id>/items/<int:item_id>/eliminar", endpoint="eliminar_item")
@login_required
@role_required("ADMIN", "OPERADOR")
def eliminar_item_legacy(solicitud_id: int, item_id: int):
    return item_eliminar(item_id)


@bp.get("/<int:solicitud_id>/editar")
@login_required
@role_required("ADMIN", "OPERADOR")
def editar(solicitud_id: int):
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))


# ============================================================
# Imprimir PDF (incluye todas las secciones del folio)
# ============================================================
@bp.get("/<int:solicitud_id>/imprimir.pdf")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def imprimir_pdf(solicitud_id: int):
    """
    Genera PDF (Carta) para Solicitud de Fondos usando WeasyPrint.

    Incluye TODO el contenido del folio:
      - Secciones sin ítems => imprime "Sin ítems"
      - REMU (QUINCENA) => se imprime desde resumen anticipos (no desde items)
      - REMU (FIN_MES)  => se imprime desde sueldos integrados (remu_sueldos_cards)
      - REMU fallback => si no hay sueldo_detalle_id / anticipo_detalle_id, resume desde ítems REMU ya integrados
      - REND => se imprime resumido por usuario (igual que detalle)
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        flash(
            "Motor PDF no disponible (falta WeasyPrint o dependencias). "
            "Instala WeasyPrint en el contenedor para habilitar impresión.",
            "error",
        )
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    solicitud: SolicitudFondos = SolicitudFondos.query.get_or_404(solicitud_id)
    _require_solicitud_access(solicitud)

    items: List[SolicitudFondosItem] = (
        SolicitudFondosItem.query
        .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
        .options(
            selectinload(SolicitudFondosItem.tercero),
            selectinload(SolicitudFondosItem.trabajador),
        )
        .order_by(SolicitudFondosItem.id.asc())
        .all()
    )

    items_by_seccion = _build_items_by_seccion(items)
    tot = _totales_por_seccion(items)

    resumen_anticipos = None
    is_quincena = (solicitud.periodo_tipo or "").upper().strip() == "QUINCENA"
    is_fin_mes = (solicitud.periodo_tipo or "").upper().strip() == "FIN_MES"

    if is_quincena:
        ref_date = solicitud.periodo_desde or solicitud.fecha_solicitud
        try:
            from ...services.anticipos_reader import get_resumen_anticipos_para_quincena  # noqa

            resumen_anticipos = get_resumen_anticipos_para_quincena(
                centro_costo=(solicitud.centro_costo or "").strip(),
                anio=int(ref_date.year),
                mes=int(ref_date.month),
            )
        except Exception:
            resumen_anticipos = None

    if resumen_anticipos:
        tot["REMU"] = _to_decimal_money(getattr(resumen_anticipos, "total_monto", None))

    def _tipo_sort_key_pdf(k: str):
        kk = (k or "").upper().strip()
        if kk in ("JEFATURA U OTROS", "JEFATURA Y OTROS"):
            return (0, kk)
        if kk == "DIRECTO":
            return (1, kk)
        return (2, kk)

    remu_anticipos_cards: List[dict] = []

    if is_quincena:
        try:
            items_remu_anticipos = (
                SolicitudFondosItem.query
                .filter(
                    SolicitudFondosItem.solicitud_id == solicitud.id,
                    SolicitudFondosItem.seccion == "REMU",
                    SolicitudFondosItem.anticipo_detalle_id.isnot(None),
                )
                .options(
                    joinedload(SolicitudFondosItem.anticipo_nomina),
                    joinedload(SolicitudFondosItem.anticipo_detalle).joinedload(AnticipoDetalle.trabajador),
                )
                .order_by(SolicitudFondosItem.id.asc())
                .all()
            )

            by_nomina: dict[int, dict] = {}

            for it in items_remu_anticipos:
                nom = getattr(it, "anticipo_nomina", None)
                det = getattr(it, "anticipo_detalle", None)
                if not nom or not det:
                    continue

                nid = int(getattr(nom, "id", 0) or 0)
                if not nid:
                    continue

                if nid not in by_nomina:
                    by_nomina[nid] = {
                        "nomina": nom,
                        "por_tipo_monto": defaultdict(Decimal),
                        "por_tipo_ids": defaultdict(set),
                        "total": Decimal("0.00"),
                    }

                t = getattr(det, "trabajador", None)
                tipo_raw = getattr(t, "tipo_trabajador", None) if t else None
                tipo = (tipo_raw or "SIN TIPO").strip() if isinstance(tipo_raw, str) else (tipo_raw or "SIN TIPO")

                monto = _to_decimal_money(getattr(det, "monto", None))

                by_nomina[nid]["por_tipo_monto"][tipo] += monto
                by_nomina[nid]["total"] += monto

                tid = getattr(t, "id", None) if t else None
                if tid:
                    by_nomina[nid]["por_tipo_ids"][tipo].add(int(tid))

            for data in by_nomina.values():
                por_tipo_list = []
                for tipo, total_tipo in data["por_tipo_monto"].items():
                    cant = len(data["por_tipo_ids"].get(tipo, set()))
                    por_tipo_list.append((tipo, total_tipo, cant))

                por_tipo_list.sort(key=lambda x: _tipo_sort_key_pdf(x[0]))

                remu_anticipos_cards.append(
                    {
                        "nomina": data["nomina"],
                        "subtotales_tipo": por_tipo_list,
                        "total": data["total"],
                    }
                )

            remu_anticipos_cards.sort(
                key=lambda x: (
                    int(getattr(x["nomina"], "anio", 0) or 0),
                    int(getattr(x["nomina"], "mes", 0) or 0),
                    int(getattr(x["nomina"], "id", 0) or 0),
                )
            )

            if (not resumen_anticipos) and remu_anticipos_cards:
                tot["REMU"] = sum([c["total"] for c in remu_anticipos_cards], Decimal("0.00"))

        except Exception:
            remu_anticipos_cards = []

    if is_quincena and (not resumen_anticipos) and (not remu_anticipos_cards):
        try:
            items_remu = items_by_seccion.get("REMU", []) if items_by_seccion else []
            if items_remu:
                subt_monto = defaultdict(Decimal)
                subt_ids = defaultdict(set)
                total = Decimal("0.00")

                for it in items_remu:
                    tr = getattr(it, "trabajador", None)
                    if tr:
                        tipo_raw = getattr(tr, "tipo_trabajador", None)
                        tipo = (str(tipo_raw).strip() if tipo_raw else "SIN TIPO") or "SIN TIPO"
                        tid = getattr(tr, "id", None)
                        if tid:
                            subt_ids[tipo].add(int(tid))
                    else:
                        tipo = "JEFATURA U OTROS"

                    monto = _to_decimal_money(getattr(it, "monto", None))
                    subt_monto[tipo] += monto
                    total += monto

                subt_list = []
                for tipo, monto_tipo in subt_monto.items():
                    cant = len(subt_ids.get(tipo, set()))
                    subt_list.append((tipo, monto_tipo, cant))

                subt_list.sort(key=lambda x: _tipo_sort_key_pdf(x[0]))

                remu_anticipos_cards = [
                    {
                        "nomina": None,
                        "subtotales_tipo": subt_list,
                        "total": total,
                    }
                ]
                tot["REMU"] = total
        except Exception:
            pass

    remu_sueldos_cards: List[dict] = []

    if is_fin_mes:
        try:
            items_remu_sueldos = (
                SolicitudFondosItem.query
                .filter(
                    SolicitudFondosItem.solicitud_id == solicitud.id,
                    SolicitudFondosItem.seccion == "REMU",
                    SolicitudFondosItem.sueldo_detalle_id.isnot(None),
                )
                .options(
                    joinedload(SolicitudFondosItem.sueldo_nomina),
                    joinedload(SolicitudFondosItem.sueldo_detalle).joinedload(SueldoDetalle.trabajador),
                    joinedload(SolicitudFondosItem.sueldo_detalle).joinedload(SueldoDetalle.contrato),
                )
                .order_by(SolicitudFondosItem.id.asc())
                .all()
            )

            by_nomina: dict[int, dict] = {}

            for it in items_remu_sueldos:
                nom = getattr(it, "sueldo_nomina", None)
                det = getattr(it, "sueldo_detalle", None)
                if not nom or not det:
                    continue

                nid = int(getattr(nom, "id", 0) or 0)
                if not nid:
                    continue

                if nid not in by_nomina:
                    by_nomina[nid] = {
                        "nomina": nom,
                        "por_tipo_monto": defaultdict(Decimal),
                        "por_tipo_ids": defaultdict(set),
                        "total": Decimal("0.00"),
                    }

                t = getattr(det, "trabajador", None)
                tipo_raw = getattr(t, "tipo_trabajador", None) if t else None
                tipo = (tipo_raw or "SIN TIPO").strip() if isinstance(tipo_raw, str) else (tipo_raw or "SIN TIPO")

                monto = _to_decimal_money(getattr(det, "liquido", None))

                by_nomina[nid]["por_tipo_monto"][tipo] += monto
                by_nomina[nid]["total"] += monto

                tid = getattr(t, "id", None) if t else None
                if tid:
                    by_nomina[nid]["por_tipo_ids"][tipo].add(int(tid))

            for data in by_nomina.values():
                por_tipo_list = []
                for tipo, total_tipo in data["por_tipo_monto"].items():
                    cant = len(data["por_tipo_ids"].get(tipo, set()))
                    por_tipo_list.append((tipo, total_tipo, cant))

                por_tipo_list.sort(key=lambda x: _tipo_sort_key_pdf(x[0]))

                remu_sueldos_cards.append(
                    {
                        "nomina": data["nomina"],
                        "subtotales_tipo": por_tipo_list,
                        "total": data["total"],
                    }
                )

            remu_sueldos_cards.sort(
                key=lambda x: (
                    int(getattr(x["nomina"], "anio", 0) or 0),
                    int(getattr(x["nomina"], "mes", 0) or 0),
                    int(getattr(x["nomina"], "id", 0) or 0),
                )
            )

            if (not resumen_anticipos) and remu_sueldos_cards:
                tot["REMU"] = sum([c["total"] for c in remu_sueldos_cards], Decimal("0.00"))

        except Exception:
            remu_sueldos_cards = []

        if (not resumen_anticipos) and (not remu_sueldos_cards):
            try:
                items_remu = items_by_seccion.get("REMU", []) if items_by_seccion else []
                if items_remu:
                    subt_monto = defaultdict(Decimal)
                    subt_ids = defaultdict(set)
                    total = Decimal("0.00")

                    for it in items_remu:
                        tr = getattr(it, "trabajador", None)
                        if tr:
                            tipo_raw = getattr(tr, "tipo_trabajador", None)
                            tipo = (str(tipo_raw).strip() if tipo_raw else "SIN TIPO") or "SIN TIPO"
                            tid = getattr(tr, "id", None)
                            if tid:
                                subt_ids[tipo].add(int(tid))
                        else:
                            tipo = "JEFATURA U OTROS"

                        monto = _to_decimal_money(getattr(it, "monto", None))
                        subt_monto[tipo] += monto
                        total += monto

                    subt_list = []
                    for tipo, monto_tipo in subt_monto.items():
                        cant = len(subt_ids.get(tipo, set()))
                        subt_list.append((tipo, monto_tipo, cant))

                    subt_list.sort(key=lambda x: _tipo_sort_key_pdf(x[0]))

                    remu_sueldos_cards = [
                        {
                            "nomina": None,
                            "subtotales_tipo": subt_list,
                            "total": total,
                        }
                    ]
                    tot["REMU"] = total
            except Exception:
                pass

    items_rend = items_by_seccion.get("REND", []) if items_by_seccion else []
    items_terc = items_by_seccion.get("TERC", []) if items_by_seccion else []
    items_var = items_by_seccion.get("VAR", []) if items_by_seccion else []

    def _fmt_rut_from_user(u) -> str | None:
        if not u:
            return None
        rut_completo = getattr(u, "rut_completo", None)
        if rut_completo:
            return str(rut_completo)
        rut = getattr(u, "rut", None)
        if rut:
            return str(rut)
        rut_num = getattr(u, "rut_num", None)
        dv = getattr(u, "dv", None)
        if rut_num and dv:
            return f"{rut_num}-{dv}"
        return None

    def _nombre_usuario(u) -> str | None:
        if not u:
            return None
        nombre = getattr(u, "nombre", None) or getattr(u, "first_name", None)
        apellido = getattr(u, "apellido", None) or getattr(u, "last_name", None)
        if nombre and apellido:
            return f"{nombre} {apellido}"
        if nombre:
            return str(nombre)
        return str(getattr(u, "username", None) or getattr(u, "email", None) or getattr(u, "id", None))

    def _rendicion_fk_filter(model, solicitud_id_val: int):
        if hasattr(model, "solicitud_fondos_id"):
            return getattr(model, "solicitud_fondos_id") == solicitud_id_val
        if hasattr(model, "solicitud_id"):
            return getattr(model, "solicitud_id") == solicitud_id_val
        if hasattr(model, "solicitudfondos_id"):
            return getattr(model, "solicitudfondos_id") == solicitud_id_val
        return sa.text("1=0")

    resumen_rendiciones: List[dict] = []
    total_rendiciones = Decimal("0.00")

    try:
        opts = [selectinload(RendicionGasto.items)]
        if hasattr(RendicionGasto, "creado_por"):
            opts.append(selectinload(RendicionGasto.creado_por))
        elif hasattr(RendicionGasto, "usuario"):
            opts.append(selectinload(RendicionGasto.usuario))
        elif hasattr(RendicionGasto, "user"):
            opts.append(selectinload(RendicionGasto.user))

        rendiciones = (
            RendicionGasto.query
            .filter(_rendicion_fk_filter(RendicionGasto, solicitud.id))
            .options(*opts)
            .order_by(RendicionGasto.id.asc())
            .all()
        )

        for r in rendiciones:
            r_items = getattr(r, "items", None) or []
            r_total = sum([(it.monto or Decimal("0.00")) for it in r_items], Decimal("0.00"))
            total_rendiciones += r_total

            u = getattr(r, "creado_por", None) or getattr(r, "usuario", None) or getattr(r, "user", None)

            resumen_rendiciones.append(
                {
                    "rendicion_id": r.id,
                    "rendicion_numero": getattr(r, "numero", None) or r.id,
                    "usuario_nombre": _nombre_usuario(u),
                    "usuario_rut": _fmt_rut_from_user(u),
                    "total": r_total,
                }
            )

        if resumen_rendiciones:
            tot["REND"] = total_rendiciones

    except Exception:
        resumen_rendiciones = []

    total_rend = tot.get("REND", Decimal("0.00"))
    total_terc = tot.get("TERC", Decimal("0.00"))
    total_var = tot.get("VAR", Decimal("0.00"))
    total_general = sum(tot.values()) if tot else Decimal("0.00")

    obra_nombre = None
    centro_costo = (solicitud.centro_costo or "").strip() or None

    obra = getattr(solicitud, "obra", None)
    if obra:
        obra_nombre = getattr(obra, "nombre", None)
        if (getattr(obra, "centro_costo", "") or "").strip():
            centro_costo = (obra.centro_costo or "").strip()

    solicitado_por = None

    try:
        html = render_template(
            "solicitudes_fondos/solicitudes_fondos_imprimir_pdf.html",
            solicitud=solicitud,
            secciones=SECCIONES,
            items_by_seccion=items_by_seccion,
            tot=tot,
            total_general=total_general,
            resumen_anticipos=resumen_anticipos,
            items_rend=items_rend,
            items_terc=items_terc,
            items_var=items_var,
            total_rend=total_rend,
            total_terc=total_terc,
            total_var=total_var,
            obra_nombre=obra_nombre,
            centro_costo=centro_costo,
            solicitado_por=solicitado_por,
            badge_estado=_badge_class_estado,
            resumen_rendiciones=resumen_rendiciones,
            remu_sueldos_cards=remu_sueldos_cards,
            remu_anticipos_cards=remu_anticipos_cards,
        )
    except TemplateError as e:
        flash(f"Error template impresión PDF: {e}", "error")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=solicitud_id))

    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    fecha_str = ""
    if getattr(solicitud, "fecha_solicitud", None):
        fecha_str = solicitud.fecha_solicitud.strftime("%Y-%m-%d")

    folio = solicitud.numero or solicitud.id
    cc = (centro_costo or "").strip() or "SIN_CC"

    filename = f"{fecha_str} Folio Nro. {folio} - {cc}.pdf"
    filename = filename.replace("/", "-").replace("\\", "-").replace(":", "-")

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Surrogate-Control"] = "no-store"
    return resp




# ============================================================
# Reportes Solicitudes de Fondos
# ============================================================
@bp.get("/reportes")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def reportes_solicitudes_fondos():
    centros_costos = _centros_costos_accesibles()

    cc = (request.args.get("centro_costo") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    periodo_tipo = (request.args.get("periodo_tipo") or "").strip().upper()
    desde = request.args.get("desde") or ""
    hasta = request.args.get("hasta") or ""

    q_sol = SolicitudFondos.query
    if not current_user.has_role("ADMIN"):
        q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centros_costos or ["__SIN_CC__"]))

    if cc:
        _assert_access_cc(cc)
        q_sol = q_sol.filter(SolicitudFondos.centro_costo == cc)
    if estado in ESTADOS:
        q_sol = q_sol.filter(SolicitudFondos.estado == estado)
    if periodo_tipo in ("QUINCENA", "FIN_MES", "OTRO"):
        q_sol = q_sol.filter(SolicitudFondos.periodo_tipo == periodo_tipo)

    try:
        if desde:
            q_sol = q_sol.filter(SolicitudFondos.fecha_solicitud >= datetime.strptime(desde, "%Y-%m-%d").date())
        if hasta:
            q_sol = q_sol.filter(SolicitudFondos.fecha_solicitud <= datetime.strptime(hasta, "%Y-%m-%d").date())
    except ValueError:
        flash("Rango de fechas inválido.", "warning")

    solicitudes = q_sol.order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc()).all()
    sol_ids = [int(s.id) for s in solicitudes]

    resumen = {}
    for s in solicitudes:
        key = (s.centro_costo or "SIN CC").strip() or "SIN CC"
        resumen.setdefault(key, {"cc": key, "solicitudes": 0, "REMU": Decimal("0"), "REND": Decimal("0"), "TERC": Decimal("0"), "VAR": Decimal("0"), "TOTAL": Decimal("0")})
        resumen[key]["solicitudes"] += 1

    if sol_ids:
        rows = (
            db.session.query(
                SolicitudFondos.centro_costo,
                SolicitudFondosItem.seccion,
                sa.func.coalesce(sa.func.sum(SolicitudFondosItem.monto), 0),
            )
            .join(SolicitudFondosItem, SolicitudFondosItem.solicitud_id == SolicitudFondos.id)
            .filter(SolicitudFondos.id.in_(sol_ids))
            .group_by(SolicitudFondos.centro_costo, SolicitudFondosItem.seccion)
            .all()
        )
        for centro, seccion, total in rows:
            key = (centro or "SIN CC").strip() or "SIN CC"
            sec = (seccion or "").strip().upper()
            if key in resumen and sec in resumen[key]:
                resumen[key][sec] += _to_decimal_money(total)

        try:
            rendiciones = (
                RendicionGasto.query
                .filter(RendicionGasto.solicitud_fondos_id.in_(sol_ids))
                .options(selectinload(RendicionGasto.items), joinedload(RendicionGasto.solicitud_fondos))
                .all()
            )
            for r in rendiciones:
                sf = getattr(r, "solicitud_fondos", None)
                key = ((getattr(sf, "centro_costo", None) or "SIN CC").strip() or "SIN CC")
                if key not in resumen:
                    continue
                total_r = sum([(it.monto or Decimal("0.00")) for it in (getattr(r, "items", None) or [])], Decimal("0.00"))
                resumen[key]["REND"] += _to_decimal_money(total_r)
        except Exception:
            pass

    for row in resumen.values():
        row["TOTAL"] = row["REMU"] + row["REND"] + row["TERC"] + row["VAR"]

    resumen_rows = sorted(resumen.values(), key=lambda x: x["TOTAL"], reverse=True)
    totales = {"solicitudes": sum(r["solicitudes"] for r in resumen_rows)}
    for sec in ("REMU", "REND", "TERC", "VAR", "TOTAL"):
        totales[sec] = sum([r[sec] for r in resumen_rows], Decimal("0"))

    return render_template(
        "solicitudes_fondos/reportes.html",
        centros_costos=centros_costos,
        estados=ESTADOS,
        periodos=PERIODOS,
        centro_costo=cc,
        estado=estado,
        periodo_tipo=periodo_tipo,
        desde=desde,
        hasta=hasta,
        resumen_rows=resumen_rows,
        totales=totales,
        fmt_clp_text=_fmt_clp_text,
    )


# ============================================================
# Nóminas Bancarias (Solicitudes de Fondos) - REND / TERC / VAR
# ============================================================
@bp.get("/nominas-banco")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco():
    centros_costos = _centros_costos_accesibles()

    # Empleadores accesibles por obras (referencia)
    empleador_ids = (
        db.session.query(sa.distinct(Obra.empleador_id))
        .filter(Obra.empleador_id.isnot(None))
        .all()
    )
    empleador_ids = [int(x[0]) for x in empleador_ids if x and x[0]]

    empleadores = []
    if empleador_ids:
        empleadores = (
            Empleador.query
            .filter(Empleador.id.in_(empleador_ids))
            .order_by(Empleador.razon_social.asc())
            .all()
        )

    # default_periodo: última solicitud accesible (APROBADA/PAGADA preferente)
    q = SolicitudFondos.query
    if not current_user.has_role("ADMIN"):
        if centros_costos:
            q = q.filter(SolicitudFondos.centro_costo.in_(centros_costos))
        else:
            q = q.filter(sa.text("1=0"))

    q = q.filter(SolicitudFondos.estado.in_(["APROBADA", "PAGADA"])).order_by(SolicitudFondos.fecha_solicitud.desc())
    last = q.first()
    default_periodo = None
    if last and getattr(last, "fecha_solicitud", None):
        d = last.fecha_solicitud
        default_periodo = f"{int(d.year):04d}-{int(d.month):02d}"

    form = {
        "plantilla": "PAGOS_PROV",
        "periodo": default_periodo,
        "periodo_tipo": "",  # ✅ NUEVO: "" = todos; QUINCENA; FIN_MES
        "centro_costos": [],
        "empresa_ids": [],
        "incluir_aprobadas": True,
        "incluir_pagadas": True,
        "tipo_pago": "",
    }

    return render_template(
        "solicitudes_fondos/solicitudes_fondos_nominas_banco.html",
        centros_costos=centros_costos,
        empleadores=empleadores,
        default_periodo=default_periodo,
        form=form,
        resultado=None,
    )


@bp.post("/nominas-banco/generar")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_generar():
    centros_costos_access = _centros_costos_accesibles()

    plantilla = (request.form.get("plantilla") or "").strip().upper()
    if plantilla not in ("PAGOS_PROV",):
        flash("Plantilla inválida.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    periodo = (request.form.get("periodo") or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})", periodo or "")
    if not m:
        flash("Período inválido. Usa formato YYYY-MM.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    anio = int(m.group(1))
    mes = int(m.group(2))
    if mes < 1 or mes > 12:
        flash("Mes inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    centro_costos = request.form.getlist("centro_costos") or []
    centro_costos = [(c or "").strip() for c in centro_costos if (c or "").strip()]

    empresa_ids_raw = request.form.getlist("empresa_ids") or []
    empresa_ids: list[int] = []
    for x in empresa_ids_raw:
        try:
            empresa_ids.append(int(x))
        except Exception:
            pass

    incluir_aprobadas = bool(request.form.get("incluir_aprobadas"))
    incluir_pagadas = bool(request.form.get("incluir_pagadas"))

    # ✅ filtro tipo de pago ("" | TRANSFERENCIA | NOMINA_2)
    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper()
    if tipo_pago not in ("", "TRANSFERENCIA", "NOMINA_2"):
        tipo_pago = ""

    # ✅ filtro corte: "" | QUINCENA | FIN_MES
    periodo_tipo = (request.form.get("periodo_tipo") or "").strip().upper()
    if periodo_tipo not in ("", "QUINCENA", "FIN_MES"):
        periodo_tipo = ""

    periodo_tipo_label = {"": "Todos", "QUINCENA": "Quincena", "FIN_MES": "Fin de mes"}.get(periodo_tipo, "Todos")

    estados = []
    if incluir_aprobadas:
        estados.append("APROBADA")
    if incluir_pagadas:
        estados.append("PAGADA")
    if not estados:
        estados = ["APROBADA", "PAGADA"]

    # Control acceso CC
    if not current_user.has_role("ADMIN"):
        if centro_costos:
            for cc in centro_costos:
                _assert_access_cc(cc)
        else:
            centro_costos = list(centros_costos_access)

    # Rango fechas del mes
    try:
        d1 = date(anio, mes, 1)
        d2 = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    except Exception:
        flash("Período inválido.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    # Query solicitudes elegibles
    q_sol = (
        SolicitudFondos.query
        .filter(
            SolicitudFondos.fecha_solicitud >= d1,
            SolicitudFondos.fecha_solicitud < d2,
            SolicitudFondos.estado.in_(estados),
        )
        .options(joinedload(SolicitudFondos.obra))
    )

    if centro_costos:
        q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centro_costos))

    if empresa_ids:
        q_sol = q_sol.join(Obra, SolicitudFondos.obra_id == Obra.id).filter(Obra.empleador_id.in_(empresa_ids))

    # ✅ NUEVO: no mezclar QUINCENA y FIN_MES dentro del mismo mes
    if periodo_tipo:
        q_sol = q_sol.filter(SolicitudFondos.periodo_tipo == periodo_tipo)

    solicitudes = q_sol.order_by(SolicitudFondos.fecha_solicitud.asc(), SolicitudFondos.id.asc()).all()
    sol_ids = [int(s.id) for s in solicitudes]

    # ---------------------------------------------------------------------
    # Caso sin resultados
    # ---------------------------------------------------------------------
    if not sol_ids:
        form = {
            "plantilla": plantilla,
            "periodo": periodo,
            "periodo_tipo": periodo_tipo,
            "centro_costos": centro_costos,
            "empresa_ids": empresa_ids,
            "incluir_aprobadas": incluir_aprobadas,
            "incluir_pagadas": incluir_pagadas,
            "tipo_pago": tipo_pago,
        }

        resultado = {
            "periodo": periodo,
            "periodo_tipo": periodo_tipo,
            "periodo_tipo_label": periodo_tipo_label,
            "plantilla_label": "Pago Proveedores Santander",
            "solicitudes_count": 0,
            "items_count": 0,
            "ok_count": 0,
            "excluidos_count": 0,
            "total_monto": 0,
            "excluidos": [],
            "download_token": None,
        }

        return render_template(
            "solicitudes_fondos/solicitudes_fondos_nominas_banco.html",
            centros_costos=centros_costos_access,
            empleadores=Empleador.query.order_by(Empleador.razon_social.asc()).all(),
            default_periodo=periodo,
            form=form,
            resultado=resultado,
        )

    # mapa solicitud_id -> label glosa (preferimos OBRA nombre; fallback CC)
    sol_label: dict[int, str] = {}
    for s in solicitudes:
        try:
            if getattr(s, "obra", None) and (getattr(s.obra, "nombre", None) or "").strip():
                label = str(s.obra.nombre).strip().upper()
            else:
                label = (getattr(s, "centro_costo", "") or "").strip().upper()
        except Exception:
            label = (getattr(s, "centro_costo", "") or "").strip().upper()
        sol_label[int(s.id)] = label or "SIN REFERENCIA"

    def _get_solicitud_id_from_rend(r) -> int | None:
        for attr in ("solicitud_fondos_id", "solicitud_id", "solicitudfondos_id"):
            v = getattr(r, attr, None)
            if v:
                try:
                    return int(v)
                except Exception:
                    return None
        return None

    # ------------------------------------------------------------
    # Query ítems: SOLO TERC/VAR (filtrables por tipo_pago)
    # ------------------------------------------------------------
    items_q = (
        SolicitudFondosItem.query
        .filter(
            SolicitudFondosItem.solicitud_id.in_(sol_ids),
            SolicitudFondosItem.seccion.in_(["TERC", "VAR"]),
        )
    )
    if tipo_pago:
        items_q = items_q.filter(SolicitudFondosItem.tipo_pago == tipo_pago)

    items = (
        items_q.options(
            joinedload(SolicitudFondosItem.tercero).joinedload(Tercero.banco),
            joinedload(SolicitudFondosItem.trabajador).joinedload(Trabajador.banco),
            joinedload(SolicitudFondosItem.solicitud),
        )
        .order_by(SolicitudFondosItem.solicitud_id.asc(), SolicitudFondosItem.id.asc())
        .all()
    )

    # ============================================================
    # REND: construir filas desde RendicionGasto (NO desde SF items)
    # ✅ REND SIEMPRE ES NOMINA_2
    # -> si tipo_pago == TRANSFERENCIA => NO incluir REND
    # -> si tipo_pago == NOMINA_2 o "" => incluir REND
    # ============================================================
    incluir_rend = (tipo_pago in ("", "NOMINA_2"))

    def _rut_plain_from_user(u) -> str | None:
        if not u:
            return None
        rut_completo = getattr(u, "rut_completo", None)
        if rut_completo:
            return re.sub(r"[^0-9K]", "", str(rut_completo).strip().upper().replace(".", "").replace(" ", ""))
        rut = getattr(u, "rut", None)
        if rut:
            return re.sub(r"[^0-9K]", "", str(rut).strip().upper().replace(".", "").replace(" ", ""))
        rut_num = getattr(u, "rut_num", None)
        dv = getattr(u, "dv", None)
        if rut_num and dv:
            return f"{re.sub(r'[^0-9]', '', str(rut_num))}{str(dv).strip().upper()}"
        return None

    def _split_rut_plain(rut_plain: str) -> tuple[str, str] | tuple[None, None]:
        s = (rut_plain or "").strip().upper()
        s = re.sub(r"[^0-9K]", "", s)
        if len(s) < 2:
            return (None, None)
        return (s[:-1], s[-1])

    def _account_plain(v) -> str:
        return re.sub(r"\D", "", str(v).strip()) if v is not None else ""

    def _email_or_fallback(v) -> str:
        e = (str(v).strip() if v is not None else "")
        return e if e else "transferencias@grupo-cs.cl"

    ok_rows_rend: list[ProveedorRow] = []
    excluidos_rend: list[dict] = []

    if incluir_rend:
        opts = [selectinload(RendicionGasto.items)]
        if hasattr(RendicionGasto, "creado_por"):
            opts.append(selectinload(RendicionGasto.creado_por))
        elif hasattr(RendicionGasto, "usuario"):
            opts.append(selectinload(RendicionGasto.usuario))
        elif hasattr(RendicionGasto, "user"):
            opts.append(selectinload(RendicionGasto.user))

        if hasattr(RendicionGasto, "solicitud_fondos_id"):
            fk_filter = RendicionGasto.solicitud_fondos_id.in_(sol_ids)
        elif hasattr(RendicionGasto, "solicitud_id"):
            fk_filter = RendicionGasto.solicitud_id.in_(sol_ids)
        elif hasattr(RendicionGasto, "solicitudfondos_id"):
            fk_filter = RendicionGasto.solicitudfondos_id.in_(sol_ids)
        else:
            fk_filter = sa.text("1=0")

        rendiciones = (
            RendicionGasto.query
            .filter(fk_filter)
            .options(*opts)
            .order_by(RendicionGasto.id.asc())
            .all()
        )

        for r in rendiciones:
            r_items = getattr(r, "items", None) or []
            total_r = sum([(it.monto or Decimal("0.00")) for it in r_items], Decimal("0.00"))
            if total_r <= 0:
                excluidos_rend.append({
                    "item_id": getattr(r, "id", None),
                    "seccion": "REND",
                    "motivo": "Rendición total <= 0",
                    "rut": None,
                    "nombre": None,
                })
                continue

            u = getattr(r, "creado_por", None) or getattr(r, "usuario", None) or getattr(r, "user", None)

            rut_plain = _rut_plain_from_user(u)
            rut_num, dv = _split_rut_plain(rut_plain or "")

            if not rut_num or not dv:
                excluidos_rend.append({
                    "item_id": getattr(r, "id", None),
                    "seccion": "REND",
                    "motivo": "RUT usuario inválido/vacío en rendición",
                    "rut": rut_plain,
                    "nombre": getattr(u, "username", None) or getattr(u, "email", None),
                })
                continue

            t = (
                Trabajador.query
                .filter(
                    sa.func.replace(Trabajador.rut, ".", "") == str(rut_num),
                    sa.func.upper(Trabajador.dv) == str(dv).upper(),
                )
                .options(joinedload(Trabajador.banco))
                .first()
            )

            if not t:
                excluidos_rend.append({
                    "item_id": getattr(r, "id", None),
                    "seccion": "REND",
                    "motivo": "No existe Trabajador con el RUT del usuario (match fallido)",
                    "rut": f"{rut_num}-{dv}",
                    "nombre": getattr(u, "username", None) or getattr(u, "email", None),
                })
                continue

            banco_code = str(getattr(getattr(t, "banco", None), "codigo_sbif", "") or "").strip()
            cuenta = _account_plain(getattr(t, "cuenta_numero", None) or getattr(t, "cuenta_rut", None))

            if not banco_code or not re.fullmatch(r"\d{1,10}", banco_code):
                excluidos_rend.append({
                    "item_id": getattr(r, "id", None),
                    "seccion": "REND",
                    "motivo": f"Código banco inválido: {banco_code or '(vacío)'}",
                    "rut": f"{rut_num}{dv}",
                    "nombre": f"{t.ap_paterno} {t.ap_materno} {t.nombres}".strip(),
                })
                continue

            if not cuenta:
                excluidos_rend.append({
                    "item_id": getattr(r, "id", None),
                    "seccion": "REND",
                    "motivo": "Cuenta destino inválida/vacía",
                    "rut": f"{rut_num}{dv}",
                    "nombre": f"{t.ap_paterno} {t.ap_materno} {t.nombres}".strip(),
                })
                continue

            nombre_b = " ".join([
                str(getattr(t, "ap_paterno", "") or "").strip(),
                str(getattr(t, "ap_materno", "") or "").strip(),
                str(getattr(t, "nombres", "") or "").strip(),
            ]).strip()

            sid = _get_solicitud_id_from_rend(r)
            label = sol_label.get(int(sid or 0), "SIN REFERENCIA") if sid else "SIN REFERENCIA"

            ok_rows_rend.append(
                ProveedorRow(
                    item_id=int(getattr(r, "id", 0) or 0),
                    seccion="REND",
                    centro_costo=(label or "").strip(),
                    rut_beneficiario=f"{rut_num}{dv}",
                    nombre_beneficiario=nombre_b,
                    codigo_banco=banco_code,
                    cuenta_destino=cuenta,
                    email_beneficiario=_email_or_fallback(getattr(t, "correo", None) or getattr(u, "email", None)),
                    nro_fact_1="999999999",
                    monto=total_r,
                    glosa=f"Rendición de gastos - {label}".strip(),
                )
            )

    # Build TERC/VAR desde SF items (ya filtrados por tipo_pago si aplica)
    build = build_proveedor_rows_from_sf_items(items)
    ok_rows = ok_rows_rend + build.ok_rows
    excluidos = excluidos_rend + build.excluidos

    total_monto = sum([r.monto for r in ok_rows], Decimal("0"))

    # XLSX
    try:
        template_filename = TEMPLATE_PAGOS_PROV
        template_path = get_template_path(current_app.root_path, template_filename)
        wb = build_xlsx_from_template(
            template_path=template_path,
            template_kind="PAGOS_PROV",
            rows=ok_rows,
            anio=anio,
            mes=mes,
            glosa=None,  # glosa viene por fila
        )
        bio = BytesIO()
        wb.save(bio)
        xlsx_bytes = bio.getvalue()
    except Exception as e:
        flash(f"No se pudo construir el XLSX: {e}", "danger")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    token = uuid.uuid4().hex
    _SF_NOMINAS_CACHE[token] = xlsx_bytes

    form = {
        "plantilla": plantilla,
        "periodo": periodo,
        "periodo_tipo": periodo_tipo,
        "centro_costos": centro_costos,
        "empresa_ids": empresa_ids,
        "incluir_aprobadas": incluir_aprobadas,
        "incluir_pagadas": incluir_pagadas,
        "tipo_pago": tipo_pago,
    }

    resultado = {
        "periodo": periodo,
        "periodo_tipo": periodo_tipo,
        "periodo_tipo_label": periodo_tipo_label,
        "plantilla_label": "Pago Proveedores Santander",
        "solicitudes_count": len(solicitudes),
        "items_count": len(items),  # TERC/VAR filtrados por tipo_pago si aplica
        "ok_count": len(ok_rows),
        "excluidos_count": len(excluidos),
        "total_monto": float(total_monto),
        "excluidos": excluidos,
        "download_token": token,
    }

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()
    return render_template(
        "solicitudes_fondos/solicitudes_fondos_nominas_banco.html",
        centros_costos=centros_costos_access,
        empleadores=empleadores,
        default_periodo=periodo,
        form=form,
        resultado=resultado,
    )

@bp.post("/nominas-banco/preparar")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_preparar():
    centros_costos_access = _centros_costos_accesibles()

    plantilla = (request.form.get("plantilla") or "").strip().upper()
    if plantilla not in ("PAGOS_PROV",):
        flash("Plantilla inválida.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    periodo = (request.form.get("periodo") or "").strip()
    anio, mes = _parse_periodo_ym(periodo)
    if not anio or not mes:
        flash("Período inválido. Usa formato YYYY-MM.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    centro_costos = [(c or "").strip() for c in (request.form.getlist("centro_costos") or []) if (c or "").strip()]

    empresa_ids: list[int] = []
    for x in (request.form.getlist("empresa_ids") or []):
        try:
            empresa_ids.append(int(x))
        except Exception:
            pass

    incluir_aprobadas = bool(request.form.get("incluir_aprobadas"))
    incluir_pagadas = bool(request.form.get("incluir_pagadas"))

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper()
    if tipo_pago not in ("", "TRANSFERENCIA", "NOMINA_2"):
        tipo_pago = ""

    periodo_tipo = (request.form.get("periodo_tipo") or "").strip().upper()
    if periodo_tipo not in ("", "QUINCENA", "FIN_MES"):
        periodo_tipo = ""

    estados = []
    if incluir_aprobadas:
        estados.append("APROBADA")
    if incluir_pagadas:
        estados.append("PAGADA")
    if not estados:
        estados = ["APROBADA", "PAGADA"]

    if not current_user.has_role("ADMIN"):
        if centro_costos:
            for cc in centro_costos:
                _assert_access_cc(cc)
        else:
            centro_costos = list(centros_costos_access)

    data = collect_nomina_candidates(
        anio=anio,
        mes=mes,
        estados=estados,
        centros_costos=centro_costos,
        empresa_ids=empresa_ids,
        tipo_pago=tipo_pago,
        periodo_tipo=periodo_tipo,
        user_is_admin=current_user.has_role("ADMIN"),
        centros_costos_access=centros_costos_access,
    )

    empleador_ids_q = (
        db.session.query(sa.distinct(Obra.empleador_id))
        .filter(Obra.empleador_id.isnot(None))
    )

    empleador_ids = [int(x[0]) for x in empleador_ids_q.all() if x and x[0]]

    empleadores = []
    if empleador_ids:
        empleadores = (
            Empleador.query
            .filter(Empleador.id.in_(empleador_ids))
            .order_by(Empleador.razon_social.asc())
            .all()
        )

    form = {
        "plantilla": plantilla,
        "periodo": periodo,
        "periodo_tipo": periodo_tipo,
        "centro_costos": centro_costos,
        "empresa_ids": empresa_ids,
        "incluir_aprobadas": incluir_aprobadas,
        "incluir_pagadas": incluir_pagadas,
        "tipo_pago": tipo_pago,
    }

    total_pendiente = sum([c.monto_pendiente for c in data["candidates"]], Decimal("0"))

    return render_template(
        "solicitudes_fondos/solicitudes_fondos_nominas_banco_preparar.html",
        centros_costos=centros_costos_access,
        empleadores=empleadores,
        form=form,
        candidates=data["candidates"],
        excluidos=data["excluidos"],
        total_pendiente=total_pendiente,
        estados=estados,
        periodo_label=periodo,
        periodo_tipo_label={"": "Todos", "QUINCENA": "Quincena", "FIN_MES": "Fin de mes"}.get(periodo_tipo, "Todos"),
        fmt_clp_text=_fmt_clp_text,
    )


@bp.post("/nominas-banco/guardar")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_guardar():
    plantilla = (request.form.get("plantilla") or "").strip().upper()
    periodo = (request.form.get("periodo") or "").strip()
    anio, mes = _parse_periodo_ym(periodo)

    if plantilla not in ("PAGOS_PROV",) or not anio or not mes:
        flash("Datos base inválidos para guardar la nómina.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    periodo_tipo = (request.form.get("periodo_tipo") or "").strip().upper()
    if periodo_tipo not in ("", "QUINCENA", "FIN_MES"):
        periodo_tipo = ""

    tipo_pago = (request.form.get("tipo_pago") or "").strip().upper()
    if tipo_pago not in ("", "TRANSFERENCIA", "NOMINA_2"):
        tipo_pago = ""

    observaciones = (request.form.get("observaciones") or "").strip() or None

    selected_keys = request.form.getlist("selected_keys")
    if not selected_keys:
        flash("Debes seleccionar al menos una línea para generar la nómina.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    selected_payload = []

    for key in selected_keys:
        safe = re.sub(r"[^A-Z0-9:_-]", "", key or "")
        if not safe:
            continue

        origen_tipo = (request.form.get(f"origen_tipo__{safe}") or "").strip().upper()
        seccion = (request.form.get(f"seccion__{safe}") or "").strip().upper()

        solicitud_id = request.form.get(f"solicitud_id__{safe}", type=int)
        solicitud_item_id = request.form.get(f"solicitud_item_id__{safe}", type=int)
        rendicion_gasto_id = request.form.get(f"rendicion_gasto_id__{safe}", type=int)

        rut_beneficiario = (request.form.get(f"rut_beneficiario__{safe}") or "").strip() or None
        nombre_beneficiario = (request.form.get(f"nombre_beneficiario__{safe}") or "").strip()
        codigo_banco = (request.form.get(f"codigo_banco__{safe}") or "").strip() or None
        cuenta_destino = (request.form.get(f"cuenta_destino__{safe}") or "").strip() or None
        email_beneficiario = (request.form.get(f"email_beneficiario__{safe}") or "").strip() or None
        nro_documento = (request.form.get(f"nro_documento__{safe}") or "").strip() or None
        glosa = (request.form.get(f"glosa__{safe}") or "").strip() or None
        descripcion = (request.form.get(f"descripcion__{safe}") or "").strip() or None

        monto_original = _to_decimal_money(request.form.get(f"monto_original__{safe}"))
        monto_pendiente = _to_decimal_money(request.form.get(f"monto_pendiente__{safe}"))
        monto_pagar = _to_decimal_money(request.form.get(f"monto_pagar__{safe}"))

        if not nombre_beneficiario:
            continue
        if monto_pagar <= 0:
            continue
        if monto_pagar > monto_pendiente:
            flash(f"El monto a pagar no puede superar el pendiente ({safe}).", "warning")
            return redirect(url_for("solicitudes_fondos.nominas_banco"))

        if origen_tipo == "SF_ITEM" and not solicitud_item_id:
            flash(f"Registro inválido: falta solicitud_item_id ({safe}).", "warning")
            return redirect(url_for("solicitudes_fondos.nominas_banco"))

        if origen_tipo == "RENDICION" and not rendicion_gasto_id:
            flash(f"Registro inválido: falta rendicion_gasto_id ({safe}).", "warning")
            return redirect(url_for("solicitudes_fondos.nominas_banco"))

        selected_payload.append({
            "origen_tipo": origen_tipo,
            "solicitud_id": solicitud_id,
            "solicitud_item_id": solicitud_item_id,
            "rendicion_gasto_id": rendicion_gasto_id,
            "seccion": seccion,
            "rut_beneficiario": rut_beneficiario,
            "nombre_beneficiario": nombre_beneficiario,
            "codigo_banco": codigo_banco,
            "cuenta_destino": cuenta_destino,
            "email_beneficiario": email_beneficiario,
            "nro_documento": nro_documento,
            "glosa": glosa,
            "descripcion": descripcion,
            "monto_original": monto_original,
            "monto_pagado_en_esta_nomina": monto_pagar,
        })

    if not selected_payload:
        flash("No se generó ninguna línea válida para la nómina.", "warning")
        return redirect(url_for("solicitudes_fondos.nominas_banco"))

    filtros_json = {
        "periodo": periodo,
        "periodo_tipo": periodo_tipo or None,
        "tipo_pago": tipo_pago or None,
        "centro_costos": request.form.getlist("centro_costos") or [],
        "empresa_ids": request.form.getlist("empresa_ids") or [],
        "incluir_aprobadas": bool(request.form.get("incluir_aprobadas")),
        "incluir_pagadas": bool(request.form.get("incluir_pagadas")),
    }

    nomina = create_nomina_from_candidates(
        current_user_id=current_user.id if current_user.is_authenticated else None,
        plantilla=plantilla,
        anio=anio,
        mes=mes,
        periodo_tipo=periodo_tipo,
        tipo_pago=tipo_pago,
        observaciones=observaciones,
        filtros_json=filtros_json,
        selected_payload=selected_payload,
    )

    flash(f"Nómina bancaria #{nomina.numero} generada correctamente.", "success")
    return redirect(url_for("solicitudes_fondos.nominas_banco_detalle", nomina_id=nomina.id))


@bp.get("/nominas-banco/<int:nomina_id>")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_detalle(nomina_id: int):
    nomina = (
        SolicitudFondosNominaBanco.query
        .options(
            joinedload(SolicitudFondosNominaBanco.creado_por),
            selectinload(SolicitudFondosNominaBanco.detalles),
        )
        .get_or_404(nomina_id)
    )

    return render_template(
        "solicitudes_fondos/solicitudes_fondos_nomina_banco_detalle.html",
        nomina=nomina,
        fmt_clp_text=_fmt_clp_text,
    )


@bp.get("/nominas-banco/<int:nomina_id>/descargar")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_descargar_persistida(nomina_id: int):
    nomina = (
        SolicitudFondosNominaBanco.query
        .options(selectinload(SolicitudFondosNominaBanco.detalles))
        .get_or_404(nomina_id)
    )

    try:
        xlsx_bytes = build_xlsx_from_nomina(
            root_path=current_app.root_path,
            nomina=nomina,
        )
    except Exception as e:
        flash(f"No se pudo construir el XLSX: {e}", "danger")
        return redirect(url_for("solicitudes_fondos.nominas_banco_detalle", nomina_id=nomina.id))

    filename = (
        f"{date.today().strftime('%Y-%m-%d')} "
        f"Nomina SF #{nomina.numero} - Pago Proveedores Santander.xlsx"
    )

    resp = make_response(xlsx_bytes)
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@bp.get("/nominas-banco/historico")
@login_required
@role_required("ADMIN", "OPERADOR")
def nominas_banco_historico():
    periodo = (request.args.get("periodo") or "").strip()
    estado = (request.args.get("estado") or "").strip().upper()
    page = request.args.get("page", 1, type=int)
    per_page = 30

    # ------------------------------------------------------------
    # Base liviana para filtros / count / IDs
    # ------------------------------------------------------------
    q_base = SolicitudFondosNominaBanco.query

    if periodo:
        anio, mes = _parse_periodo_ym(periodo)
        if anio and mes:
            q_base = q_base.filter(
                SolicitudFondosNominaBanco.periodo_anio == anio,
                SolicitudFondosNominaBanco.periodo_mes == mes,
            )

    if estado in ("BORRADOR", "GENERADA", "PAGADA", "ANULADA"):
        q_base = q_base.filter(SolicitudFondosNominaBanco.estado == estado)

    total = q_base.order_by(None).count()

    offset = max(page - 1, 0) * per_page

    ids_rows = (
        q_base.with_entities(SolicitudFondosNominaBanco.id)
        .order_by(
            SolicitudFondosNominaBanco.fecha_generacion.desc(),
            SolicitudFondosNominaBanco.id.desc(),
        )
        .offset(offset)
        .limit(per_page)
        .all()
    )

    nomina_ids = [int(r[0]) for r in ids_rows if r and r[0]]

    detalles_count_sq = (
        db.session.query(
            SolicitudFondosNominaBancoDetalle.nomina_id.label("nomina_id"),
            sa.func.count(SolicitudFondosNominaBancoDetalle.id).label("detalles_count"),
        )
        .group_by(SolicitudFondosNominaBancoDetalle.nomina_id)
        .subquery()
    )

    nominas = []

    if nomina_ids:
        rows = (
            db.session.query(
                SolicitudFondosNominaBanco.id,
                SolicitudFondosNominaBanco.numero,
                SolicitudFondosNominaBanco.periodo_anio,
                SolicitudFondosNominaBanco.periodo_mes,
                SolicitudFondosNominaBanco.periodo_tipo,
                SolicitudFondosNominaBanco.tipo_pago,
                SolicitudFondosNominaBanco.estado,
                SolicitudFondosNominaBanco.fecha_generacion,
                SolicitudFondosNominaBanco.total_monto,
                SolicitudFondosNominaBanco.observaciones,
                User.nombre.label("creado_por_nombre"),
                sa.func.coalesce(detalles_count_sq.c.detalles_count, 0).label("detalles_count"),
            )
            .outerjoin(User, SolicitudFondosNominaBanco.creado_por_user_id == User.id)
            .outerjoin(
                detalles_count_sq,
                detalles_count_sq.c.nomina_id == SolicitudFondosNominaBanco.id,
            )
            .filter(SolicitudFondosNominaBanco.id.in_(nomina_ids))
            .all()
        )

        def _periodo_tipo_label(v: str | None) -> str:
            x = (v or "").strip().upper()
            return {
                "QUINCENA": "Quincena",
                "FIN_MES": "Fin de mes",
            }.get(x, "Todos")

        def _tipo_pago_label(v: str | None) -> str:
            x = (v or "").strip().upper()
            return {
                "TRANSFERENCIA": "Transferencia",
                "NOMINA_2": "Nómina 2",
            }.get(x, "Todos")

        def _estado_label(v: str | None) -> str:
            x = (v or "").strip().upper()
            return {
                "BORRADOR": "Borrador",
                "GENERADA": "Generada",
                "PAGADA": "Pagada",
                "ANULADA": "Anulada",
            }.get(x, x.title() if x else "-")

        rows_map = {}
        for r in rows:
            rows_map[int(r.id)] = {
                "id": int(r.id),
                "numero": r.numero,
                "periodo_ym": f"{int(r.periodo_anio):04d}-{int(r.periodo_mes):02d}",
                "periodo_tipo_label": _periodo_tipo_label(r.periodo_tipo),
                "tipo_pago_label": _tipo_pago_label(r.tipo_pago),
                "estado": r.estado,
                "estado_label": _estado_label(r.estado),
                "fecha_generacion": r.fecha_generacion,
                "total_monto": r.total_monto,
                "observaciones": r.observaciones,
                "creado_por_nombre": r.creado_por_nombre,
                "_detalles_count": int(r.detalles_count or 0),
            }

        nominas = [rows_map[nid] for nid in nomina_ids if nid in rows_map]

    pagination = SimplePagination(page=page, per_page=per_page, total=total)

    return render_template(
        "solicitudes_fondos/solicitudes_fondos_nominas_banco_historico.html",
        nominas=nominas,
        pagination=pagination,
        periodo=periodo,
        estado=estado,
        fmt_clp_text=_fmt_clp_text,
    )


@bp.post("/<int:solicitud_id>/volver-a-borrador")
@login_required
@role_required("ADMIN")
def volver_a_borrador(solicitud_id: int):
    s = SolicitudFondos.query.get_or_404(solicitud_id)

    estado_actual = (s.estado or "").strip().upper()

    # Solo permitimos rollback desde APROBADA -> BORRADOR
    if estado_actual != "APROBADA":
        flash("Acción no permitida: la solicitud no está en estado APROBADA.", "warning")
        return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))

    s.estado = "BORRADOR"
    _sf_registrar_movimiento(
        s,
        "REVERSION_ADMIN",
        "Solicitud revertida a BORRADOR por corrección administrativa.",
        estado_anterior=estado_actual,
        estado_nuevo="BORRADOR",
    )
    db.session.add(s)
    db.session.commit()

    flash("Solicitud revertida a BORRADOR. Ya puedes editar y corregir la información ✅", "success")
    return redirect(url_for("solicitudes_fondos.detalle", solicitud_id=s.id))