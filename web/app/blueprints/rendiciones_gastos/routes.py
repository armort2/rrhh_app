# web/app/blueprints/rendiciones_gastos/routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Set, Iterable, Optional, Tuple
from functools import lru_cache
from sqlalchemy.exc import IntegrityError

import re
import sqlalchemy as sa
from flask import render_template, request, redirect, url_for, flash, abort, make_response
from flask_login import current_user, login_required

from ...extensions import db
from ...models import (
    Obra,
    SolicitudFondos,
    SolicitudFondosItem,
    RendicionGasto,
    RendicionGastoItem,
    RendicionCentroCostoAutorizado,
    User,
)
from . import bp


ESTADOS_REND = ["BORRADOR", "ENVIADA", "APROBADA", "RECHAZADA", "INTEGRADA"]


CONCEPTOS_RENDICION = [
    "Combustible",
    "Peaje",
    "Movilización",
    "Artículos de oficina",
    "Útiles de aseo",
    "Notaría",
    "Material de construcción",
    "Herramientas",
    "Equipos y arriendo de equipos",
    "Estacionamiento",
    "Correspondencia",
    "Insumos",
    "Repuestos",
    "Mantención y reparación",
    "Agua",
    "Electricidad",
    "Gas",
    "Internet y telefonía",
    "Aseo",
    "Alimentación",
    "Hospedaje",
    "Tratos",
    "Bonos",
    "Remuneraciones",
    "Imposiciones",
    "Permisos y derechos municipales",
    "Multas",
    "Servicios profesionales",
    "Seguridad",
    "Otros gastos operacionales",
]

TIPOS_DOCUMENTO_RENDICION = [
    "Factura",
    "Factura exenta",
    "Boleta",
    "Boleta de honorarios",
    "Comprobante",
    "Egreso",
    "Acuerdo de Pago",
    "Guía de despacho",
    "Vale",
    "Recibo",
    "Transferencia",
    "Orden de compra",
    "Cotización",
    "Sin documento",
    "Otro",
]

def _normalizar_opcion_catalogo(valor: str | None, catalogo: list[str]) -> str | None:
    """
    Normaliza valores de selects controlados, tolerando mayúsculas/minúsculas
    y espacios accidentales. Devuelve el valor canónico del catálogo.
    """
    valor_limpio = (valor or "").strip()
    if not valor_limpio:
        return None

    valor_key = re.sub(r"\s+", " ", valor_limpio).casefold()
    for opcion in catalogo:
        opcion_key = re.sub(r"\s+", " ", opcion).casefold()
        if valor_key == opcion_key:
            return opcion
    return None


# -------------------------
# Helpers generales
# -------------------------

def _safe_filename(s: str) -> str:
    """Normaliza y sanitiza nombres de archivo para Content-Disposition."""
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r'[\\/:"*?<>|]+', "-", s)
    return s

def _user_display(u: User | None) -> tuple[str | None, str | None]:
    """
    Devuelve (nombre_display, username)
    - nombre_display: prioriza campos "humanos" si existen
    - username: fallback identificador
    """
    if not u:
        return (None, None)

    username = (getattr(u, "username", None) or getattr(u, "user", None) or None)
    username = (str(username).strip() if username else None)

    # Prioridad: nombre visible (según tu modelo User existe "nombre")
    for attr in ("nombre", "nombre_completo", "full_name", "name", "nombres"):
        v = getattr(u, attr, None)
        if v and str(v).strip():
            return (str(v).strip(), username)

    if username:
        return (username, username)

    # Último recurso
    uid = getattr(u, "id", None)
    return (f"UID{uid}" if uid else None, username)


def _parse_iso_date_or_none(value: str | None) -> date | None:
    """Parsea fechas YYYY-MM-DD desde filtros GET sin botar el listado por una URL manual inválida."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _usuarios_con_rendiciones(privileged: bool) -> list[dict]:
    """Usuarios que tienen rendiciones registradas, para poblar el filtro del listado."""
    q = (
        sa.select(
            User.id.label("id"),
            User.username.label("username"),
            User.nombre.label("nombre"),
        )
        .join(RendicionGasto, RendicionGasto.creado_por_user_id == User.id)
        .distinct()
    )

    if not privileged:
        try:
            q = q.where(User.id == int(current_user.id))
        except Exception:
            q = q.where(sa.false())

    # Ordenamos en Python para evitar el error de PostgreSQL:
    # SELECT DISTINCT + ORDER BY exige que la expresión de orden esté en el SELECT.
    usuarios = []
    for row in db.session.execute(q).all():
        display = (row.nombre or row.username or f"Usuario #{row.id}").strip()
        username = (row.username or "").strip()
        usuarios.append({
            "id": row.id,
            "display": display,
            "username": username,
        })

    usuarios.sort(key=lambda u: (u.get("display") or u.get("username") or "").casefold())
    return usuarios

# -------------------------
# Roles / permisos
# -------------------------

def _has_role(role_name: str) -> bool:
    if not getattr(current_user, "is_authenticated", False):
        return False

    role_u = (role_name or "").strip().upper()
    if not role_u:
        return False

    # UID desde sesión Flask-Login (fuente de verdad)
    try:
        uid = int(current_user.get_id() or 0)
    except Exception:
        uid = 0
    if uid <= 0:
        return False

    # 1) Método del modelo
    try:
        if hasattr(current_user, "has_role"):
            if bool(current_user.has_role(role_u)):
                return True
    except Exception:
        pass

    # 2) Relación roles (si viene cargada)
    try:
        roles = getattr(current_user, "roles", None) or []
        for r in roles:
            n = (getattr(r, "name", None) or "").strip().upper()
            if n == role_u:
                return True
    except Exception:
        pass

    # 3) Fallback SQL (autoridad final)
    try:
        q = sa.text("""
            select 1
            from user_roles ur
            join roles r on r.id = ur.role_id
            where ur.user_id = :uid
              and upper(btrim(r.name)) = :role
            limit 1
        """)
        return bool(db.session.execute(q, {"uid": uid, "role": role_u}).scalar())
    except Exception:
        return False


def _is_admin() -> bool:
    return _has_role("ADMIN")


def _is_operador() -> bool:
    return _has_role("OPERADOR")


def _is_revisor() -> bool:
    return _has_role("REVISOR")


def _is_hmoya() -> bool:
    try:
        return (getattr(current_user, "username", "") or "").strip().lower() == "hmoya"
    except Exception:
        return False


def _is_privileged_all() -> bool:
    return _is_admin() or _is_hmoya()


# -------------------------
# Centros de costo / helpers
# -------------------------

def _find_user_obras_pivot_table() -> Optional[Tuple[str, str, str]]:
    try:
        insp = sa.inspect(db.engine)
        table_names = set(insp.get_table_names())
    except Exception:
        return None

    candidates = [
        "user_obras",
        "users_obras",
        "usuario_obras",
        "usuarios_obras",
        "user_obra",
        "users_obra",
        "usuario_obra",
        "usuarios_obra",
    ]

    for t in candidates:
        if t in table_names:
            try:
                cols = {c["name"] for c in insp.get_columns(t)}
            except Exception:
                continue

            user_col = None
            obra_col = None

            for uc in ("user_id", "usuario_id", "users_id"):
                if uc in cols:
                    user_col = uc
                    break
            for oc in ("obra_id", "obras_id"):
                if oc in cols:
                    obra_col = oc
                    break

            if user_col and obra_col:
                return (t, user_col, obra_col)

    for t in table_names:
        if "obra" not in t:
            continue
        try:
            cols = {c["name"] for c in insp.get_columns(t)}
        except Exception:
            continue

        user_col = None
        obra_col = None

        for uc in ("user_id", "usuario_id", "users_id"):
            if uc in cols:
                user_col = uc
                break
        for oc in ("obra_id", "obras_id"):
            if oc in cols:
                obra_col = oc
                break

        if user_col and obra_col:
            return (t, user_col, obra_col)

    return None


@lru_cache(maxsize=1)
def _cached_user_obras_pivot_table() -> Optional[Tuple[str, str, str]]:
    """
    ✅ Cachea el hallazgo de la tabla pivote user<->obras para evitar inspect() por request.
    """
    return _find_user_obras_pivot_table()


def _centros_costos_desde_obras_usuario() -> Set[str]:
    if not getattr(current_user, "is_authenticated", False):
        return set()

    if hasattr(current_user, "obras"):
        try:
            obras = getattr(current_user, "obras") or []
            ccs = {
                str(getattr(o, "centro_costo", "")).strip()
                for o in obras
                if getattr(o, "centro_costo", None) and str(getattr(o, "centro_costo")).strip()
            }
            return {cc for cc in ccs if cc}
        except Exception:
            pass

    pivot = _cached_user_obras_pivot_table()
    if not pivot:
        return set()

    table_name, user_col, obra_col = pivot

    pivot_tbl = sa.table(
        table_name,
        sa.column(user_col),
        sa.column(obra_col),
    )

    rows = (
        db.session.execute(
            sa.select(Obra.centro_costo)
            .select_from(pivot_tbl.join(Obra, getattr(pivot_tbl.c, obra_col) == Obra.id))
            .where(getattr(pivot_tbl.c, user_col) == int(current_user.id))
            .where(
                Obra.centro_costo.isnot(None),
                sa.func.btrim(Obra.centro_costo) != "",
            )
            .distinct()
            .order_by(Obra.centro_costo.asc())
        )
        .scalars()
        .all()
    )

    return {str(r).strip() for r in rows if r and str(r).strip()}


def _centros_costos_autorizados() -> Set[str]:
    """
    Regla:
      - ADMIN o hmoya: acceso total (set vacío)
      - Otros:
          1) si tiene explícitos => usar esos
          2) si NO => derivar desde obras
    """
    if _is_privileged_all():
        return set()

    rows = (
        db.session.execute(
            sa.select(RendicionCentroCostoAutorizado.centro_costo)
            .where(RendicionCentroCostoAutorizado.user_id == current_user.id)
            .where(RendicionCentroCostoAutorizado.vigente.is_(True))
        )
        .scalars()
        .all()
    )
    explicit = {str(r).strip() for r in rows if r and str(r).strip()}
    if explicit:
        return explicit

    return _centros_costos_desde_obras_usuario()


def _can_access_cc(centro_costo: str) -> bool:
    cc = (centro_costo or "").strip()
    if not cc:
        return False
    if _is_privileged_all():
        return True
    return cc in _centros_costos_autorizados()


def _can_access_rendicion(r: RendicionGasto) -> bool:
    """
    Regla:
      - ADMIN o hmoya: pueden entrar a todas (respetando CC)
      - Otros: solo pueden entrar a rendiciones creadas por ellos (y además CC autorizado)
    """
    if not _can_access_cc(getattr(r, "centro_costo", None) or ""):
        return False

    if _is_privileged_all():
        return True

    try:
        return int(getattr(r, "creado_por_user_id", 0) or 0) == int(current_user.id)
    except Exception:
        return False


def _solo_lectura() -> bool:
    return _is_revisor()


def _parse_decimal(val: str | None) -> Decimal:
    if val is None:
        return Decimal("0")

    s = str(val).strip()
    if not s:
        return Decimal("0")

    s = s.replace(" ", "")

    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        if s.count(".") == 1 and re.match(r"^\d+\.\d{1,2}$", s):
            pass
        else:
            s = s.replace(".", "")

    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _next_numero_for_cc(centro_costo: str) -> int:
    maxn = (
        db.session.execute(
            sa.select(sa.func.max(RendicionGasto.numero)).where(RendicionGasto.centro_costo == centro_costo)
        )
        .scalar()
        or 0
    )
    return int(maxn) + 1


def _distinct_cc_from_obras() -> list[str]:
    return (
        db.session.execute(
            sa.select(Obra.centro_costo)
            .where(
                Obra.centro_costo.isnot(None),
                sa.func.btrim(Obra.centro_costo) != "",
            )
            .distinct()
            .order_by(Obra.centro_costo.asc())
        )
        .scalars()
        .all()
    )


def _distinct_cc_from_rendiciones() -> list[str]:
    return (
        db.session.execute(
            sa.select(RendicionGasto.centro_costo)
            .where(
                RendicionGasto.centro_costo.isnot(None),
                sa.func.btrim(RendicionGasto.centro_costo) != "",
            )
            .distinct()
            .order_by(RendicionGasto.centro_costo.asc())
        )
        .scalars()
        .all()
    )


def _count_items(rendicion_id: int) -> int:
    return int(
        db.session.execute(
            sa.select(sa.func.count())
            .select_from(RendicionGastoItem)
            .where(RendicionGastoItem.rendicion_id == rendicion_id)
        ).scalar()
        or 0
    )


def _is_solicitud_cerrada(s: SolicitudFondos | None) -> bool:
    if not s:
        return False
    return (s.estado or "").upper().strip() in {"PAGADA", "RECHAZADA"}


def _rendicion_editable(r: RendicionGasto) -> bool:
    if _is_revisor():
        return False

    estado = (r.estado or "").upper().strip()
    if estado not in {"BORRADOR", "INTEGRADA"}:
        return False

    if estado == "INTEGRADA" and r.solicitud_fondos_id:
        s = db.session.get(SolicitudFondos, int(r.solicitud_fondos_id))
        if _is_solicitud_cerrada(s):
            return False

    return True


def _sync_rendicion_to_solicitud(r: RendicionGasto) -> tuple[bool, str | None]:
    """
    Sincroniza ítems de rendición a SolicitudFondosItem (sección REND).
    Ahora permite montos negativos en REND, siempre que la BD tenga
    la constraint ajustada para aceptar negativos en esa sección.
    """
    if not r.solicitud_fondos_id:
        return (True, None)

    s = db.session.get(SolicitudFondos, int(r.solicitud_fondos_id))
    if not s:
        return (True, None)

    if (s.centro_costo or "").strip() != (r.centro_costo or "").strip():
        return (False, "La Solicitud de Fondos vinculada no corresponde al mismo Centro de Costo.")

    if _is_solicitud_cerrada(s):
        return (False, "La Solicitud de Fondos vinculada está cerrada y no admite re-sincronización.")

    items = (
        db.session.execute(
            sa.select(RendicionGastoItem)
            .where(RendicionGastoItem.rendicion_id == r.id)
            .order_by(RendicionGastoItem.orden.asc())
        )
        .scalars()
        .all()
    )

    prefix = f"RG{r.id}-"

    try:
        db.session.execute(
            sa.delete(SolicitudFondosItem).where(
                SolicitudFondosItem.solicitud_id == s.id,
                SolicitudFondosItem.seccion == "REND",
                SolicitudFondosItem.control_interno.isnot(None),
                SolicitudFondosItem.control_interno.like(f"{prefix}%"),
            )
        )

        for it in items:
            doc_pack = ""
            if it.tipo_doc or it.nro_doc:
                doc_pack = f"{(it.tipo_doc or 'COMPROBANTE')}|{(it.nro_doc or '')}".strip("|")

            desc_parts: list[str] = []
            if it.descripcion:
                desc_parts.append(it.descripcion)
            if it.fecha:
                desc_parts.append(f"Fecha: {it.fecha.isoformat()}")
            if it.proveedor:
                desc_parts.append(f"Proveedor: {it.proveedor}")
            descripcion = " · ".join(desc_parts) if desc_parts else None

            sf_item = SolicitudFondosItem(
                solicitud_id=s.id,
                seccion="REND",
                monto=it.monto,
                tipo_pago="TRANSFERENCIA",
                nro_documento=doc_pack or None,
                concepto=(it.detalle[:80] if it.detalle else "RENDICION"),
                descripcion=descripcion,
                control_interno=f"RG{r.id}-IT{it.id}",
                beneficiario_nombre=it.proveedor or "Beneficiario no informado",
            )
            db.session.add(sf_item)

        db.session.flush()
        return (True, None)

    except IntegrityError as e:
        db.session.rollback()
        return (
            False,
            f"No fue posible sincronizar la rendición con Solicitud de Fondos: {str(e.orig)}",
        )


# -------------------------
# Rutas
# -------------------------

@bp.get("/")
@login_required
def listado():
    import time

    t0 = time.perf_counter()

    centro_costo = (request.args.get("centro_costo") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    desde = (request.args.get("desde") or "").strip()
    hasta = (request.args.get("hasta") or "").strip()
    usuario_id = (request.args.get("usuario_id") or "").strip()

    desde_fecha = _parse_iso_date_or_none(desde)
    hasta_fecha = _parse_iso_date_or_none(hasta)

    usuario_id_int = None
    if usuario_id:
        try:
            usuario_id_int = int(usuario_id)
            if usuario_id_int <= 0:
                usuario_id_int = None
                usuario_id = ""
        except Exception:
            usuario_id_int = None
            usuario_id = ""

    puede_filtrar_usuario = _is_privileged_all()

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1

    per_page = 30
    offset = (page - 1) * per_page

    # -------------------------------------------------
    # Base filter query (solo IDs / count)
    # -------------------------------------------------
    base_q = sa.select(RendicionGasto.id).select_from(RendicionGasto)

    if not puede_filtrar_usuario:
        allowed = _centros_costos_autorizados()
        if not allowed:
            base_q = base_q.where(sa.false())
        else:
            base_q = base_q.where(RendicionGasto.centro_costo.in_(sorted(allowed)))

        base_q = base_q.where(RendicionGasto.creado_por_user_id == int(current_user.id))
    elif usuario_id_int:
        base_q = base_q.where(RendicionGasto.creado_por_user_id == usuario_id_int)

    if centro_costo:
        base_q = base_q.where(RendicionGasto.centro_costo == centro_costo)
    if estado:
        base_q = base_q.where(RendicionGasto.estado == estado)
    if desde_fecha:
        base_q = base_q.where(RendicionGasto.fecha_rendicion >= desde_fecha)
    if hasta_fecha:
        base_q = base_q.where(RendicionGasto.fecha_rendicion <= hasta_fecha)

    t_build_q = time.perf_counter()

    # -------------------------------------------------
    # Count total
    # -------------------------------------------------
    base_ids_sq = base_q.subquery()

    total = (
        db.session.execute(
            sa.select(sa.func.count()).select_from(base_ids_sq)
        ).scalar()
        or 0
    )

    resumen_row = db.session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0).label("total_monto"),
            sa.func.count(RendicionGastoItem.id).label("total_items"),
        )
        .select_from(base_ids_sq)
        .outerjoin(RendicionGastoItem, RendicionGastoItem.rendicion_id == base_ids_sq.c.id)
    ).one()

    resumen = {
        "total_rendiciones": int(total or 0),
        "total_items": int(resumen_row.total_items or 0),
        "total_monto": resumen_row.total_monto or 0,
    }

    t_count = time.perf_counter()

    # -------------------------------------------------
    # IDs de la página
    # -------------------------------------------------
    page_ids = db.session.execute(
        base_q.order_by(RendicionGasto.id.desc())
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    t_page_ids = time.perf_counter()

    rows_out = []
    if page_ids:
        # Subquery agregada: total e ítems por rendición
        total_sq = (
            sa.select(
                RendicionGastoItem.rendicion_id.label("rid"),
                sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0).label("total_monto"),
                sa.func.count(sa.literal(1)).label("n_items"),
            )
            .group_by(RendicionGastoItem.rendicion_id)
            .subquery()
        )

        # Query plana: solo columnas necesarias para el listado
        q_rows = (
            sa.select(
                RendicionGasto.id.label("id"),
                RendicionGasto.numero.label("numero"),
                RendicionGasto.centro_costo.label("centro_costo"),
                RendicionGasto.fecha_rendicion.label("fecha_rendicion"),
                RendicionGasto.estado.label("estado"),
                RendicionGasto.solicitud_fondos_id.label("solicitud_fondos_id"),
                RendicionGasto.creado_en.label("creado_en"),
                RendicionGasto.actualizado_en.label("actualizado_en"),

                Obra.codigo.label("obra_codigo"),
                Obra.nombre.label("obra_nombre"),

                SolicitudFondos.numero.label("solicitud_numero"),

                User.username.label("creador_username"),
                User.nombre.label("creador_nombre"),

                sa.func.coalesce(total_sq.c.total_monto, 0).label("total_monto"),
                sa.func.coalesce(total_sq.c.n_items, 0).label("n_items"),
            )
            .select_from(RendicionGasto)
            .outerjoin(User, User.id == RendicionGasto.creado_por_user_id)
            .outerjoin(Obra, Obra.id == RendicionGasto.obra_id)
            .outerjoin(SolicitudFondos, SolicitudFondos.id == RendicionGasto.solicitud_fondos_id)
            .outerjoin(total_sq, total_sq.c.rid == RendicionGasto.id)
            .where(RendicionGasto.id.in_(page_ids))
        )

        rows = db.session.execute(q_rows).all()

        # Mantener orden original de page_ids
        rows_map = {row.id: row for row in rows}

        for rid in page_ids:
            row = rows_map.get(rid)
            if not row:
                continue

            creador_display = (row.creador_nombre or row.creador_username or "-")
            creador_username = row.creador_username or None

            ref_parts = []
            if row.obra_codigo or row.obra_nombre:
                ref_parts.append(
                    f"Ref: {(row.obra_codigo or '-')} · {(row.obra_nombre or '-')}"
                )
            else:
                ref_parts.append("—")

            if row.solicitud_numero is not None:
                ref_parts.append(f"Integrada a Solicitud #{row.solicitud_numero}")
            elif row.solicitud_fondos_id:
                ref_parts.append(f"Vinculada a Solicitud (ID) #{row.solicitud_fondos_id}")

            rows_out.append({
                "id": row.id,
                "numero": row.numero,
                "centro_costo": row.centro_costo,
                "fecha_rendicion": row.fecha_rendicion,
                "estado": row.estado,
                "solicitud_fondos_id": row.solicitud_fondos_id,
                "creado_en": row.creado_en,
                "actualizado_en": row.actualizado_en,
                "creador_display": creador_display,
                "creador_username": creador_username,
                "obra_codigo": row.obra_codigo,
                "obra_nombre": row.obra_nombre,
                "solicitud_numero": row.solicitud_numero,
                "referencia_display": " · ".join(ref_parts),
                "total_monto": row.total_monto or 0,
                "n_items": int(row.n_items or 0),
            })

    t_page_rows = time.perf_counter()

    if puede_filtrar_usuario:
        centros_costos = _distinct_cc_from_rendiciones()
    else:
        centros_costos = sorted(_centros_costos_autorizados())

    usuarios_rendiciones = _usuarios_con_rendiciones(puede_filtrar_usuario)

    total_pages = max((total + per_page - 1) // per_page, 1)

    print(
        "[REND listado timings] "
        f"build_q={t_build_q - t0:.3f}s | "
        f"count={t_count - t_build_q:.3f}s | "
        f"page_ids={t_page_ids - t_count:.3f}s | "
        f"page_rows={t_page_rows - t_page_ids:.3f}s | "
        f"total={time.perf_counter() - t0:.3f}s | "
        f"page={page} | per_page={per_page} | total_rows={total}"
    )

    return render_template(
        "rendiciones_gastos/listado.html",
        rendiciones=rows_out,
        centros_costos=centros_costos,
        estados=ESTADOS_REND,
        centro_costo=centro_costo,
        estado=estado,
        desde=desde,
        hasta=hasta,
        usuario_id=usuario_id,
        usuarios_rendiciones=usuarios_rendiciones,
        puede_filtrar_usuario=puede_filtrar_usuario,
        resumen=resumen,
        solo_lectura=_solo_lectura(),
        is_admin=_is_admin(),
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )

@bp.get("/nueva")
@login_required
def nueva():
    if _is_revisor():
        abort(403)

    if _is_privileged_all():
        centros_costos = _distinct_cc_from_obras()
        obras_q = sa.select(Obra)
    else:
        centros_costos = sorted(_centros_costos_autorizados())
        if centros_costos:
            obras_q = sa.select(Obra).where(Obra.centro_costo.in_(centros_costos))
        else:
            obras_q = sa.select(Obra).where(sa.false())

    obras = db.session.execute(obras_q.order_by(Obra.codigo.asc())).scalars().all()

    return render_template(
        "rendiciones_gastos/nueva.html",
        centros_costos=centros_costos,
        obras=obras,
        estados=ESTADOS_REND,
    )


@bp.post("/crear")
@login_required
def crear():
    if _is_revisor():
        abort(403)

    centro_costo = (request.form.get("centro_costo") or "").strip()
    if not centro_costo:
        flash("Debes seleccionar Centro de Costo.", "warning")
        return redirect(url_for("rendiciones_gastos.nueva"))

    if not _can_access_cc(centro_costo):
        abort(403)

    obra_id_raw = (request.form.get("obra_id") or "").strip()
    obra_id_int = int(obra_id_raw) if obra_id_raw else None

    fecha_rendicion_raw = (request.form.get("fecha_rendicion") or "").strip()
    periodo_desde_raw = (request.form.get("periodo_desde") or "").strip()
    periodo_hasta_raw = (request.form.get("periodo_hasta") or "").strip()
    observaciones = (request.form.get("observaciones") or "").strip() or None

    fr = date.fromisoformat(fecha_rendicion_raw) if fecha_rendicion_raw else date.today()
    pd = date.fromisoformat(periodo_desde_raw) if periodo_desde_raw else None
    ph = date.fromisoformat(periodo_hasta_raw) if periodo_hasta_raw else None

    # -----------------------------
    # Anti-duplicado operacional (server-side)
    # -----------------------------
    q_last = (
        sa.select(RendicionGasto)
        .where(RendicionGasto.creado_por_user_id == int(current_user.id))
        .where(RendicionGasto.centro_costo == centro_costo)
        .where(RendicionGasto.estado == "BORRADOR")
        .where(RendicionGasto.solicitud_fondos_id.is_(None))
        .where(RendicionGasto.fecha_rendicion == fr)
        .where(RendicionGasto.periodo_desde.is_(None) if pd is None else RendicionGasto.periodo_desde == pd)
        .where(RendicionGasto.periodo_hasta.is_(None) if ph is None else RendicionGasto.periodo_hasta == ph)
        .order_by(RendicionGasto.id.desc())
        .limit(1)
    )
    if obra_id_int is None:
        q_last = q_last.where(RendicionGasto.obra_id.is_(None))
    else:
        q_last = q_last.where(RendicionGasto.obra_id == obra_id_int)

    last = db.session.execute(q_last).scalars().first()
    if last and _count_items(int(last.id)) == 0:
        flash("Ya había una rendición en creación. Te llevé a la última generada para evitar duplicados.", "info")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=last.id))

    numero = _next_numero_for_cc(centro_costo)

    r = RendicionGasto(
        centro_costo=centro_costo,
        numero=numero,
        obra_id=obra_id_int,
        fecha_rendicion=fr,
        periodo_desde=pd,
        periodo_hasta=ph,
        estado="BORRADOR",
        observaciones=observaciones,
        creado_por_user_id=current_user.id,
    )

    db.session.add(r)
    db.session.commit()

    flash(f"Rendición #{r.numero} creada para {r.centro_costo}.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.get("/<int:rendicion_id>")
@login_required
def detalle(rendicion_id: int):
    import time

    t0 = time.perf_counter()

    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r):
        abort(403)

    solo_lectura = _solo_lectura() or (not _rendicion_editable(r) and not _is_privileged_all())

    t_rendicion = time.perf_counter()

    # -------------------------------------------------
    # Cabecera auxiliar plana (evitar lazy loads)
    # -------------------------------------------------
    obra_data = None
    if r.obra_id:
        obra_row = db.session.execute(
            sa.select(
                Obra.id,
                Obra.codigo,
                Obra.nombre,
            ).where(Obra.id == r.obra_id)
        ).first()
        if obra_row:
            obra_data = {
                "id": obra_row.id,
                "codigo": obra_row.codigo,
                "nombre": obra_row.nombre,
            }

    creador_data = None
    if r.creado_por_user_id:
        user_row = db.session.execute(
            sa.select(
                User.id,
                User.username,
                User.email,
                User.nombre,
            ).where(User.id == r.creado_por_user_id)
        ).first()
        if user_row:
            creador_data = {
                "id": user_row.id,
                "username": user_row.username,
                "email": user_row.email,
                "nombre": user_row.nombre,
            }

    t_header = time.perf_counter()

    # -------------------------------------------------
    # Items planos
    # -------------------------------------------------
    items_rows = db.session.execute(
        sa.select(
            RendicionGastoItem.id,
            RendicionGastoItem.orden,
            RendicionGastoItem.fecha,
            RendicionGastoItem.detalle,
            RendicionGastoItem.descripcion,
            RendicionGastoItem.tipo_doc,
            RendicionGastoItem.nro_doc,
            RendicionGastoItem.proveedor,
            RendicionGastoItem.monto,
        )
        .where(RendicionGastoItem.rendicion_id == r.id)
        .order_by(RendicionGastoItem.orden.asc(), RendicionGastoItem.id.asc())
    ).all()

    items = [
        {
            "id": row.id,
            "orden": row.orden,
            "fecha": row.fecha,
            "detalle": row.detalle,
            "descripcion": row.descripcion,
            "tipo_doc": row.tipo_doc,
            "nro_doc": row.nro_doc,
            "proveedor": row.proveedor,
            "monto": row.monto,
        }
        for row in items_rows
    ]

    agg_row = db.session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0).label("total"),
            sa.func.count(RendicionGastoItem.id).label("n_items"),
        )
        .where(RendicionGastoItem.rendicion_id == r.id)
    ).first()

    total = agg_row.total or 0
    n_items = int(agg_row.n_items or 0)

    t_items = time.perf_counter()

    # -------------------------------------------------
    # Solicitudes recientes (planas)
    # -------------------------------------------------
    solicitudes_rows = db.session.execute(
        sa.select(
            SolicitudFondos.id,
            SolicitudFondos.numero,
            SolicitudFondos.estado,
            SolicitudFondos.centro_costo,
        )
        .where(SolicitudFondos.centro_costo == r.centro_costo)
        .order_by(SolicitudFondos.id.desc())
        .limit(20)
    ).all()

    solicitudes = [
        {
            "id": row.id,
            "numero": row.numero,
            "estado": row.estado,
            "centro_costo": row.centro_costo,
        }
        for row in solicitudes_rows
    ]

    solicitud_vinculada = None
    if r.solicitud_fondos_id:
        sv_row = db.session.execute(
            sa.select(
                SolicitudFondos.id,
                SolicitudFondos.numero,
                SolicitudFondos.estado,
                SolicitudFondos.centro_costo,
            ).where(SolicitudFondos.id == int(r.solicitud_fondos_id))
        ).first()
        if sv_row:
            solicitud_vinculada = {
                "id": sv_row.id,
                "numero": sv_row.numero,
                "estado": sv_row.estado,
                "centro_costo": sv_row.centro_costo,
            }

    t_solicitudes = time.perf_counter()

    print(
        "[REND detalle timings] "
        f"get_r={t_rendicion - t0:.3f}s | "
        f"header={t_header - t_rendicion:.3f}s | "
        f"items={t_items - t_header:.3f}s | "
        f"solicitudes={t_solicitudes - t_items:.3f}s | "
        f"total={time.perf_counter() - t0:.3f}s | "
        f"rendicion_id={r.id} | n_items={n_items}"
    )

    return render_template(
        "rendiciones_gastos/detalle.html",
        r=r,
        obra_data=obra_data,
        creador_data=creador_data,
        items=items,
        estados=ESTADOS_REND,
        solo_lectura=solo_lectura,
        total=total,
        n_items=n_items,
        solicitudes=solicitudes,
        solicitud_vinculada=solicitud_vinculada,
        is_admin=_is_admin(),
        conceptos_rendicion=CONCEPTOS_RENDICION,
        tipos_documento_rendicion=TIPOS_DOCUMENTO_RENDICION,
    )


# ---------------------------
# Imprimir PDF (Rendición de Gastos)
# ---------------------------
@bp.get("/<int:rendicion_id>/imprimir.pdf")
@login_required
def imprimir_pdf(rendicion_id: int):
    """
    Genera PDF (Carta) para Rendición de Gastos usando WeasyPrint.
    Incluye cabecera + tabla de ítems + total.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        flash(
            "Motor PDF no disponible (falta WeasyPrint o dependencias). "
            "Instala WeasyPrint en el contenedor para habilitar impresión.",
            "error",
        )
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=rendicion_id))

    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r):
        abort(403)

    items = (
        db.session.execute(
            sa.select(RendicionGastoItem)
            .where(RendicionGastoItem.rendicion_id == r.id)
            .order_by(RendicionGastoItem.orden.asc(), RendicionGastoItem.id.asc())
        )
        .scalars()
        .all()
    )

    total = (
        db.session.execute(
            sa.select(sa.func.coalesce(sa.func.sum(RendicionGastoItem.monto), 0))
            .where(RendicionGastoItem.rendicion_id == r.id)
        )
        .scalar()
        or 0
    )

    creador_display = None
    creador_username = None
    try:
        if getattr(r, "creado_por_user_id", None):
            u = db.session.get(User, int(r.creado_por_user_id))
            creador_display, creador_username = _user_display(u)
    except Exception:
        pass

    html = render_template(
        "rendiciones_gastos/rendiciones_gastos_imprimir_pdf.html",
        r=r,
        items=items,
        total=total,
        creador_display=creador_display,
        creador_username=creador_username,
        generado_en=datetime.now(),
    )

    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()

    fecha_str = r.fecha_rendicion.isoformat() if getattr(r, "fecha_rendicion", None) else date.today().isoformat()
    nombre_creador = (
        creador_display
        or creador_username
        or (f"UID{r.creado_por_user_id}" if r.creado_por_user_id else "SinNombre")
    )
    cc = (r.centro_costo or "").strip() or "SinCC"
    filename = _safe_filename(f"{fecha_str} Rendición de gastos - {nombre_creador} ({cc}).pdf")

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.post("/<int:rendicion_id>/eliminar")
@login_required
def eliminar(rendicion_id: int):
    if not _is_admin():
        abort(403)

    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_cc(r.centro_costo):
        abort(403)

    if (r.estado or "").upper() == "INTEGRADA" or r.solicitud_fondos_id:
        flash("No se puede eliminar una rendición integrada o vinculada a Solicitud de Fondos.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    n_items = _count_items(r.id)
    if n_items > 0:
        flash("No se puede eliminar: la rendición tiene ítems. Elimina los ítems primero.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    # (siempre será 0 por la validación, pero lo dejamos por robustez)
    db.session.execute(sa.delete(RendicionGastoItem).where(RendicionGastoItem.rendicion_id == r.id))
    db.session.delete(r)
    db.session.commit()

    flash("Rendición eliminada correctamente.", "success")
    return redirect(url_for("rendiciones_gastos.listado"))


@bp.post("/<int:rendicion_id>/agregar-item")
@login_required
def item_agregar(rendicion_id: int):
    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r) or _is_revisor():
        abort(403)

    if not _rendicion_editable(r):
        flash("No puedes agregar ítems en el estado actual de la rendición.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    detalle = _normalizar_opcion_catalogo(request.form.get("detalle"), CONCEPTOS_RENDICION)
    if not detalle:
        flash("Debes seleccionar un concepto válido del listado.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    monto = _parse_decimal(request.form.get("monto"))
    if monto == 0:
        flash("El monto no puede ser 0. Usa un valor positivo o negativo.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    fecha = request.form.get("fecha") or ""
    tipo_doc = _normalizar_opcion_catalogo(request.form.get("tipo_doc"), TIPOS_DOCUMENTO_RENDICION)
    if (request.form.get("tipo_doc") or "").strip() and not tipo_doc:
        flash("Debes seleccionar un tipo de documento válido del listado.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))
    nro_doc = (request.form.get("nro_doc") or "").strip() or None
    proveedor = (request.form.get("proveedor") or "").strip() or None
    descripcion = (request.form.get("descripcion") or "").strip() or None

    max_orden = (
        db.session.execute(
            sa.select(sa.func.coalesce(sa.func.max(RendicionGastoItem.orden), 0))
            .where(RendicionGastoItem.rendicion_id == r.id)
        ).scalar()
        or 0
    )

    it = RendicionGastoItem(
        rendicion_id=r.id,
        orden=int(max_orden) + 1,
        fecha=date.fromisoformat(fecha) if fecha else None,
        detalle=detalle,
        descripcion=descripcion,
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        proveedor=proveedor,
        monto=monto,
    )
    db.session.add(it)
    db.session.commit()

    _sync_rendicion_to_solicitud(r)
    db.session.commit()

    flash("Ítem agregado.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.post("/items/<int:item_id>/eliminar")
@login_required
def item_eliminar(item_id: int):
    it = db.session.get(RendicionGastoItem, item_id)
    if not it:
        abort(404)
    r = db.session.get(RendicionGasto, it.rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r) or _is_revisor():
        abort(403)

    if not _rendicion_editable(r):
        flash("No puedes eliminar ítems en el estado actual de la rendición.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    db.session.delete(it)
    db.session.commit()

    _sync_rendicion_to_solicitud(r)
    db.session.commit()

    flash("Ítem eliminado.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.post("/items/<int:item_id>/editar")
@login_required
def item_editar(item_id: int):
    it = db.session.get(RendicionGastoItem, item_id)
    if not it:
        abort(404)

    r = db.session.get(RendicionGasto, it.rendicion_id)
    if not r:
        abort(404)

    if _is_revisor():
        abort(403)
    if not _can_access_rendicion(r):
        abort(403)

    if not _rendicion_editable(r):
        flash("No puedes editar ítems en el estado actual de la rendición.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    fecha = (request.form.get("fecha") or "").strip()
    detalle = _normalizar_opcion_catalogo(request.form.get("detalle"), CONCEPTOS_RENDICION)
    descripcion = (request.form.get("descripcion") or "").strip() or None
    tipo_doc = _normalizar_opcion_catalogo(request.form.get("tipo_doc"), TIPOS_DOCUMENTO_RENDICION)
    nro_doc = (request.form.get("nro_doc") or "").strip() or None
    proveedor = (request.form.get("proveedor") or "").strip() or None
    monto = _parse_decimal(request.form.get("monto"))

    if not detalle:
        flash("Debes seleccionar un concepto válido del listado.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    if (request.form.get("tipo_doc") or "").strip() and not tipo_doc:
        flash("Debes seleccionar un tipo de documento válido del listado.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    if monto == 0:
        flash("El monto no puede ser 0. Usa un valor positivo o negativo.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    it.fecha = date.fromisoformat(fecha) if fecha else None
    it.detalle = detalle
    it.descripcion = descripcion
    it.tipo_doc = tipo_doc
    it.nro_doc = nro_doc
    it.proveedor = proveedor
    it.monto = monto

    db.session.commit()

    _sync_rendicion_to_solicitud(r)
    db.session.commit()

    flash("Ítem actualizado.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.post("/<int:rendicion_id>/cambiar-estado")
@login_required
def cambiar_estado(rendicion_id: int):
    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r):
        abort(403)
    if _is_revisor():
        abort(403)

    nuevo = (request.form.get("estado") or "").strip().upper()
    if nuevo not in ESTADOS_REND:
        flash("Estado inválido.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    # INTEGRADA solo vía integración
    if nuevo == "INTEGRADA":
        flash("INTEGRADA solo se asigna al integrar con Solicitud de Fondos.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    estado_actual = (r.estado or "").strip().upper()

    # ✅ Reglas especiales de reversa a BORRADOR (solo ADMIN)
    if nuevo == "BORRADOR":
        if not _is_admin():
            abort(403)

        # No permitir reversa si está integrada o vinculada
        if estado_actual == "INTEGRADA" or r.solicitud_fondos_id:
            flash("No se puede volver a BORRADOR: rendición integrada o vinculada a Solicitud de Fondos.", "warning")
            return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

        # Opcional: limitar desde qué estados se puede revertir
        if estado_actual not in {"ENVIADA", "RECHAZADA"}:
            flash(f"No se puede volver a BORRADOR desde el estado {estado_actual}.", "warning")
            return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

        r.estado = "BORRADOR"
        db.session.commit()
        flash("Rendición revertida a BORRADOR (acción de administrador).", "success")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    # ✅ Flujo normal (no-admin también puede en sus estados permitidos)
    r.estado = nuevo
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.post("/<int:rendicion_id>/integrar")
@login_required
def integrar(rendicion_id: int):
    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r) or _is_revisor():
        abort(403)

    if r.estado == "INTEGRADA":
        if not r.solicitud_fondos_id:
            flash("Rendición marcada INTEGRADA pero sin solicitud vinculada.", "warning")
            return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

        req_solicitud_id = (request.form.get("solicitud_fondos_id") or "").strip()
        if req_solicitud_id and int(req_solicitud_id) != int(r.solicitud_fondos_id):
            flash(
                "Esta rendición ya está integrada. Si necesitas moverla a otra solicitud, primero desvincula (flujo futuro).",
                "warning",
            )
            return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

        _sync_rendicion_to_solicitud(r)
        db.session.commit()
        flash("Rendición re-sincronizada con la Solicitud de Fondos (REND).", "success")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    solicitud_id = (request.form.get("solicitud_fondos_id") or "").strip()
    if not solicitud_id:
        flash("Debes seleccionar una Solicitud de Fondos para integrar.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    s = db.session.get(SolicitudFondos, int(solicitud_id))
    if not s:
        flash("Solicitud de Fondos no encontrada.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    if s.centro_costo != r.centro_costo:
        flash("La Solicitud seleccionada no corresponde al mismo Centro de Costo.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    if (s.estado or "").upper() in ["PAGADA", "RECHAZADA"]:
        flash("No se puede integrar en una solicitud PAGADA/RECHAZADA.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    items = (
        db.session.execute(
            sa.select(RendicionGastoItem)
            .where(RendicionGastoItem.rendicion_id == r.id)
            .order_by(RendicionGastoItem.orden.asc())
        )
        .scalars()
        .all()
    )

    if not items:
        flash("No puedes integrar una rendición sin ítems.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    for it in items:
        doc_pack = ""
        if it.tipo_doc or it.nro_doc:
            doc_pack = f"{(it.tipo_doc or 'COMPROBANTE')}|{(it.nro_doc or '')}".strip("|")

        desc_parts: list[str] = []
        if it.descripcion:
            desc_parts.append(it.descripcion)
        if it.fecha:
            desc_parts.append(f"Fecha: {it.fecha.isoformat()}")
        if it.proveedor:
            desc_parts.append(f"Proveedor: {it.proveedor}")
        descripcion = " · ".join(desc_parts) if desc_parts else None

        sf_item = SolicitudFondosItem(
            solicitud_id=s.id,
            seccion="REND",
            monto=it.monto,
            tipo_pago="TRANSFERENCIA",
            nro_documento=doc_pack or None,
            concepto=(it.detalle[:80] if it.detalle else "RENDICION"),
            descripcion=descripcion,
            control_interno=f"RG{r.id}-IT{it.id}",
            beneficiario_nombre=it.proveedor or "Beneficiario no informado",
        )
        db.session.add(sf_item)

    r.solicitud_fondos_id = s.id
    r.estado = "INTEGRADA"
    db.session.commit()

    flash("Rendición integrada a Solicitud de Fondos (REND).", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


# -------------------------
# ADMIN: Autorizaciones por CC
# -------------------------

@bp.get("/autorizaciones")
@login_required
def autorizaciones():
    if not _is_admin():
        abort(403)

    rows = (
        db.session.execute(
            sa.select(RendicionCentroCostoAutorizado).order_by(
                RendicionCentroCostoAutorizado.centro_costo.asc(),
                RendicionCentroCostoAutorizado.user_id.asc(),
            )
        )
        .unique()
        .scalars()
        .all()
    )

    centros_costos = _distinct_cc_from_obras()

    users = (
        db.session.execute(sa.select(User).order_by(User.username.asc()))
        .unique()
        .scalars()
        .all()
    )

    return render_template(
        "rendiciones_gastos/autorizaciones.html",
        rows=rows,
        centros_costos=centros_costos,
        users=users,
    )


@bp.post("/autorizaciones/guardar")
@login_required
def autorizaciones_guardar():
    if not _is_admin():
        abort(403)

    centro_costo = (request.form.get("centro_costo") or "").strip()
    user_id = request.form.get("user_id") or ""
    vigente = (request.form.get("vigente") or "1") == "1"

    if not centro_costo or not user_id:
        flash("Debes seleccionar Centro de Costo y Usuario.", "warning")
        return redirect(url_for("rendiciones_gastos.autorizaciones"))

    row = db.session.execute(
        sa.select(RendicionCentroCostoAutorizado)
        .where(RendicionCentroCostoAutorizado.centro_costo == centro_costo)
        .where(RendicionCentroCostoAutorizado.user_id == int(user_id))
    ).scalar_one_or_none()

    if row:
        row.vigente = vigente
    else:
        row = RendicionCentroCostoAutorizado(
            centro_costo=centro_costo,
            user_id=int(user_id),
            vigente=vigente,
            created_by_user_id=current_user.id,
        )
        db.session.add(row)

    db.session.commit()
    flash("Autorización actualizada.", "success")
    return redirect(url_for("rendiciones_gastos.autorizaciones"))


@bp.post("/<int:rendicion_id>/actualizar")
@login_required
def actualizar(rendicion_id: int):
    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r) or _is_revisor():
        abort(403)

    if (r.estado or "").upper() not in {"BORRADOR", "RECHAZADA"}:
        flash("No puedes editar la cabecera en el estado actual.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    obra_id = request.form.get("obra_id")
    periodo_desde = request.form.get("periodo_desde")
    periodo_hasta = request.form.get("periodo_hasta")
    observaciones = (request.form.get("observaciones") or "").strip() or None

    if obra_id:
        obra = db.session.get(Obra, int(obra_id))
        if not obra or obra.centro_costo != r.centro_costo:
            flash("Obra inválida para el Centro de Costo.", "warning")
            return redirect(url_for("rendiciones_gastos.editar", rendicion_id=r.id))
        r.obra_id = obra.id
    else:
        r.obra_id = None

    r.periodo_desde = date.fromisoformat(periodo_desde) if periodo_desde else None
    r.periodo_hasta = date.fromisoformat(periodo_hasta) if periodo_hasta else None
    r.observaciones = observaciones

    db.session.commit()

    flash("Cabecera de la rendición actualizada.", "success")
    return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))


@bp.get("/<int:rendicion_id>/editar")
@login_required
def editar(rendicion_id: int):
    r = db.session.get(RendicionGasto, rendicion_id)
    if not r:
        abort(404)

    if not _can_access_rendicion(r) or _is_revisor():
        abort(403)

    if (r.estado or "").upper() not in {"BORRADOR", "RECHAZADA"}:
        flash("No puedes editar la cabecera en el estado actual.", "warning")
        return redirect(url_for("rendiciones_gastos.detalle", rendicion_id=r.id))

    obras = (
        db.session.execute(
            sa.select(Obra)
            .where(Obra.centro_costo == r.centro_costo)
            .order_by(Obra.codigo.asc().nullslast(), Obra.nombre.asc())
        )
        .scalars()
        .all()
    )
    editable = (r.estado or "").upper() in {"BORRADOR", "RECHAZADA"}

    return render_template(
        "rendiciones_gastos/editar.html",
        r=r,
        obras=obras,
        editable=editable,
        centros_costos=[r.centro_costo],
        estados=ESTADOS_REND,
    )