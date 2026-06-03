# web/app/services/solicitudes_fondos_nominas_banco.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any

import re
import sqlalchemy as sa
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models import (
    Empleador,
    Obra,
    RendicionGasto,
    SolicitudFondos,
    SolicitudFondosItem,
    SolicitudFondosNominaBanco,
    SolicitudFondosNominaBancoDetalle,
    Tercero,
    Trabajador,
)
from .bank_nominas import (
    ProveedorRow,
    TEMPLATE_PAGOS_PROV,
    _numero_documento_bancario,
    build_proveedor_rows_from_sf_items,
    build_xlsx_from_template,
    get_template_path,
)


@dataclass
class NominaBancoCandidate:
    origen_tipo: str              # SF_ITEM / RENDICION
    origen_id: int                # item_id o rendicion_id
    solicitud_id: int | None
    seccion: str                  # REND / TERC / VAR
    centro_costo: str | None
    solicitud_label: str | None
    rut_beneficiario: str | None
    nombre_beneficiario: str
    codigo_banco: str | None
    cuenta_destino: str | None
    email_beneficiario: str | None
    nro_documento: str | None
    glosa: str | None
    descripcion: str | None
    monto_original: Decimal
    ya_pagado: Decimal
    monto_pendiente: Decimal
    monto_sugerido: Decimal
    motivo_exclusion: str | None = None

    @property
    def key(self) -> str:
        return f"{self.origen_tipo}:{self.origen_id}"


def _to_decimal(v) -> Decimal:
    try:
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _rut_plain(v: str | None) -> str | None:
    if not v:
        return None
    s = re.sub(r"[^0-9Kk]", "", str(v).strip())
    return s.upper() or None


def _split_rut(rut_plain: str | None) -> tuple[str | None, str | None]:
    s = _rut_plain(rut_plain)
    if not s or len(s) < 2:
        return (None, None)
    return (s[:-1], s[-1])


def _account_plain(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\D", "", str(v).strip())
    return s or None


def _email_or_default(v: str | None) -> str:
    e = (v or "").strip()
    return e if e else "transferencias@grupo-cs.cl"


def _nombre_trabajador(t: Trabajador) -> str:
    return " ".join([
        str(getattr(t, "ap_paterno", "") or "").strip(),
        str(getattr(t, "ap_materno", "") or "").strip(),
        str(getattr(t, "nombres", "") or "").strip(),
    ]).strip()


def _label_solicitud(s: SolicitudFondos | None) -> str:
    if not s:
        return "SIN REFERENCIA"
    obra = getattr(s, "obra", None)
    if obra and (getattr(obra, "nombre", None) or "").strip():
        return str(obra.nombre).strip().upper()
    return (getattr(s, "centro_costo", "") or "").strip().upper() or "SIN REFERENCIA"


def next_numero_nomina_banco() -> int:
    max_num = db.session.query(sa.func.max(SolicitudFondosNominaBanco.numero)).scalar()
    return int(max_num or 0) + 1


def get_nomina_pagado_map_sf_items(item_ids: list[int]) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {int(x): Decimal("0") for x in item_ids if x}
    if not item_ids:
        return out

    rows = (
        db.session.query(
            SolicitudFondosNominaBancoDetalle.solicitud_item_id,
            sa.func.coalesce(sa.func.sum(SolicitudFondosNominaBancoDetalle.monto_pagado_en_esta_nomina), 0),
        )
        .join(
            SolicitudFondosNominaBanco,
            SolicitudFondosNominaBanco.id == SolicitudFondosNominaBancoDetalle.nomina_id,
        )
        .filter(
            SolicitudFondosNominaBancoDetalle.solicitud_item_id.in_(item_ids),
            SolicitudFondosNominaBanco.estado != "ANULADA",
        )
        .group_by(SolicitudFondosNominaBancoDetalle.solicitud_item_id)
        .all()
    )
    for item_id, total in rows:
        if item_id:
            out[int(item_id)] = _to_decimal(total)
    return out


def get_nomina_pagado_map_rendiciones(rend_ids: list[int]) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {int(x): Decimal("0") for x in rend_ids if x}
    if not rend_ids:
        return out

    rows = (
        db.session.query(
            SolicitudFondosNominaBancoDetalle.rendicion_gasto_id,
            sa.func.coalesce(sa.func.sum(SolicitudFondosNominaBancoDetalle.monto_pagado_en_esta_nomina), 0),
        )
        .join(
            SolicitudFondosNominaBanco,
            SolicitudFondosNominaBanco.id == SolicitudFondosNominaBancoDetalle.nomina_id,
        )
        .filter(
            SolicitudFondosNominaBancoDetalle.rendicion_gasto_id.in_(rend_ids),
            SolicitudFondosNominaBanco.estado != "ANULADA",
        )
        .group_by(SolicitudFondosNominaBancoDetalle.rendicion_gasto_id)
        .all()
    )
    for rend_id, total in rows:
        if rend_id:
            out[int(rend_id)] = _to_decimal(total)
    return out


def collect_nomina_candidates(
    *,
    anio: int,
    mes: int,
    estados: list[str],
    centros_costos: list[str],
    empresa_ids: list[int],
    tipo_pago: str,
    periodo_tipo: str,
    user_is_admin: bool,
    centros_costos_access: list[str],
) -> dict[str, Any]:
    q_sol = (
        SolicitudFondos.query
        .filter(
            sa.extract("year", SolicitudFondos.fecha_solicitud) == anio,
            sa.extract("month", SolicitudFondos.fecha_solicitud) == mes,
            SolicitudFondos.estado.in_(estados),
        )
        .options(joinedload(SolicitudFondos.obra))
    )

    if not user_is_admin:
        if centros_costos:
            q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centros_costos))
        else:
            q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centros_costos_access))
    elif centros_costos:
        q_sol = q_sol.filter(SolicitudFondos.centro_costo.in_(centros_costos))

    if empresa_ids:
        q_sol = q_sol.join(Obra, SolicitudFondos.obra_id == Obra.id).filter(Obra.empleador_id.in_(empresa_ids))

    if periodo_tipo:
        q_sol = q_sol.filter(SolicitudFondos.periodo_tipo == periodo_tipo)

    solicitudes = q_sol.order_by(SolicitudFondos.fecha_solicitud.asc(), SolicitudFondos.id.asc()).all()
    sol_ids = [int(s.id) for s in solicitudes]

    if not sol_ids:
        return {
            "solicitudes": [],
            "candidates": [],
            "excluidos": [],
        }

    sol_map = {int(s.id): s for s in solicitudes}

    # ------------------------------------------------------------
    # SF items: TERC / VAR
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
            joinedload(SolicitudFondosItem.solicitud).joinedload(SolicitudFondos.obra),
        )
        .order_by(SolicitudFondosItem.solicitud_id.asc(), SolicitudFondosItem.id.asc())
        .all()
    )

    item_ids = [int(x.id) for x in items]
    pagado_map_items = get_nomina_pagado_map_sf_items(item_ids)

    candidates: list[NominaBancoCandidate] = []
    excluidos: list[dict[str, Any]] = []

    build = build_proveedor_rows_from_sf_items(items)
    ok_by_item_id = {int(r.item_id): r for r in build.ok_rows if getattr(r, "item_id", None)}

    for x in build.excluidos:
        excluidos.append(dict(x))

    for it in items:
        row = ok_by_item_id.get(int(it.id))
        if not row:
            continue

        monto_original = _to_decimal(it.monto)
        ya_pagado = _to_decimal(pagado_map_items.get(int(it.id)))
        pendiente = monto_original - ya_pagado
        if pendiente <= 0:
            continue

        s = sol_map.get(int(it.solicitud_id)) if it.solicitud_id else None

        candidates.append(
            NominaBancoCandidate(
                origen_tipo="SF_ITEM",
                origen_id=int(it.id),
                solicitud_id=int(it.solicitud_id) if it.solicitud_id else None,
                seccion=(it.seccion or "").strip().upper(),
                centro_costo=(getattr(s, "centro_costo", None) or "").strip() or None,
                solicitud_label=_label_solicitud(s),
                rut_beneficiario=getattr(row, "rut_beneficiario", None),
                nombre_beneficiario=getattr(row, "nombre_beneficiario", None) or it.beneficiario_display,
                codigo_banco=getattr(row, "codigo_banco", None),
                cuenta_destino=getattr(row, "cuenta_destino", None),
                email_beneficiario=getattr(row, "email_beneficiario", None),
                nro_documento=getattr(row, "nro_fact_1", None) or _numero_documento_bancario(getattr(it, "nro_documento", None)),
                glosa=getattr(row, "glosa", None),
                descripcion=getattr(it, "descripcion", None),
                monto_original=monto_original,
                ya_pagado=ya_pagado,
                monto_pendiente=pendiente,
                monto_sugerido=pendiente,
            )
        )

    # ------------------------------------------------------------
    # REND
    # ------------------------------------------------------------
    incluir_rend = (tipo_pago in ("", "NOMINA_2"))
    if incluir_rend:
        rendiciones = (
            RendicionGasto.query
            .filter(RendicionGasto.solicitud_fondos_id.in_(sol_ids))
            .options(
                selectinload(RendicionGasto.items),
                joinedload(RendicionGasto.creado_por),
            )
            .order_by(RendicionGasto.id.asc())
            .all()
        )

        rend_ids = [int(r.id) for r in rendiciones]
        pagado_map_rend = get_nomina_pagado_map_rendiciones(rend_ids)

        for r in rendiciones:
            total_r = sum([_to_decimal(it.monto) for it in (r.items or [])], Decimal("0"))
            if total_r <= 0:
                excluidos.append({
                    "item_id": int(r.id),
                    "seccion": "REND",
                    "motivo": "Rendición total <= 0",
                    "rut": None,
                    "nombre": None,
                })
                continue

            u = getattr(r, "creado_por", None)
            rut_plain = _rut_plain(getattr(u, "rut", None))
            rut_num, dv = _split_rut(rut_plain)

            if not rut_num or not dv:
                excluidos.append({
                    "item_id": int(r.id),
                    "seccion": "REND",
                    "motivo": "RUT usuario inválido/vacío en rendición",
                    "rut": rut_plain,
                    "nombre": getattr(u, "nombre", None) or getattr(u, "email", None),
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
                excluidos.append({
                    "item_id": int(r.id),
                    "seccion": "REND",
                    "motivo": "No existe Trabajador con el RUT del usuario",
                    "rut": f"{rut_num}-{dv}",
                    "nombre": getattr(u, "nombre", None) or getattr(u, "email", None),
                })
                continue

            banco_code = str(getattr(getattr(t, "banco", None), "codigo_sbif", "") or "").strip() or None
            cuenta = _account_plain(getattr(t, "cuenta_numero", None) or getattr(t, "cuenta_rut", None))
            if not banco_code or not cuenta:
                excluidos.append({
                    "item_id": int(r.id),
                    "seccion": "REND",
                    "motivo": "Datos bancarios incompletos",
                    "rut": f"{rut_num}-{dv}",
                    "nombre": _nombre_trabajador(t),
                })
                continue

            ya_pagado = _to_decimal(pagado_map_rend.get(int(r.id)))
            pendiente = total_r - ya_pagado
            if pendiente <= 0:
                continue

            s = sol_map.get(int(r.solicitud_fondos_id)) if r.solicitud_fondos_id else None

            candidates.append(
                NominaBancoCandidate(
                    origen_tipo="RENDICION",
                    origen_id=int(r.id),
                    solicitud_id=int(r.solicitud_fondos_id) if r.solicitud_fondos_id else None,
                    seccion="REND",
                    centro_costo=(getattr(r, "centro_costo", None) or "").strip() or None,
                    solicitud_label=_label_solicitud(s),
                    rut_beneficiario=f"{rut_num}{dv}",
                    nombre_beneficiario=_nombre_trabajador(t),
                    codigo_banco=banco_code,
                    cuenta_destino=cuenta,
                    email_beneficiario=_email_or_default(getattr(t, "correo", None) or getattr(u, "email", None)),
                    nro_documento=None,
                    glosa=f"Rendición de gastos - {_label_solicitud(s)}",
                    descripcion=getattr(r, "observaciones", None),
                    monto_original=total_r,
                    ya_pagado=ya_pagado,
                    monto_pendiente=pendiente,
                    monto_sugerido=pendiente,
                )
            )

    candidates.sort(key=lambda x: (
        x.solicitud_label or "",
        x.seccion or "",
        x.nombre_beneficiario or "",
        int(x.origen_id or 0),
    ))

    return {
        "solicitudes": solicitudes,
        "candidates": candidates,
        "excluidos": excluidos,
    }


def create_nomina_from_candidates(
    *,
    current_user_id: int | None,
    plantilla: str,
    anio: int,
    mes: int,
    periodo_tipo: str,
    tipo_pago: str,
    observaciones: str | None,
    filtros_json: dict[str, Any],
    selected_payload: list[dict[str, Any]],
) -> SolicitudFondosNominaBanco:
    nomina = SolicitudFondosNominaBanco(
        numero=next_numero_nomina_banco(),
        plantilla=plantilla,
        periodo_anio=anio,
        periodo_mes=mes,
        periodo_tipo=periodo_tipo or None,
        tipo_pago=tipo_pago or None,
        estado="GENERADA",
        observaciones=(observaciones or "").strip() or None,
        filtros_json=filtros_json,
        creado_por_user_id=current_user_id,
        total_monto=Decimal("0"),
    )
    db.session.add(nomina)
    db.session.flush()

    total = Decimal("0")

    for row in selected_payload:
        detalle = SolicitudFondosNominaBancoDetalle(
            nomina_id=nomina.id,
            origen_tipo=row["origen_tipo"],
            solicitud_id=row.get("solicitud_id"),
            solicitud_item_id=row.get("solicitud_item_id"),
            rendicion_gasto_id=row.get("rendicion_gasto_id"),
            seccion=row["seccion"],
            rut_beneficiario=row.get("rut_beneficiario"),
            nombre_beneficiario=row["nombre_beneficiario"],
            codigo_banco=row.get("codigo_banco"),
            cuenta_destino=row.get("cuenta_destino"),
            email_beneficiario=row.get("email_beneficiario"),
            nro_documento=row.get("nro_documento"),
            glosa=row.get("glosa"),
            descripcion=row.get("descripcion"),
            monto_original=_to_decimal(row.get("monto_original")),
            monto_pagado_en_esta_nomina=_to_decimal(row.get("monto_pagado_en_esta_nomina")),
        )
        db.session.add(detalle)
        total += _to_decimal(detalle.monto_pagado_en_esta_nomina)

    nomina.total_monto = total
    db.session.commit()
    return nomina


def build_xlsx_from_nomina(*, root_path: str, nomina: SolicitudFondosNominaBanco) -> bytes:
    rows: list[ProveedorRow] = []

    for d in (nomina.detalles or []):
        rows.append(
            ProveedorRow(
                item_id=int(d.id),
                seccion=(d.seccion or "").strip().upper(),
                centro_costo=(d.glosa or "").strip() or "SIN REFERENCIA",
                rut_beneficiario=(d.rut_beneficiario or "").strip(),
                nombre_beneficiario=(d.nombre_beneficiario or "").strip(),
                codigo_banco=(d.codigo_banco or "").strip(),
                cuenta_destino=(d.cuenta_destino or "").strip(),
                email_beneficiario=(d.email_beneficiario or "").strip() or "transferencias@grupo-cs.cl",
                nro_fact_1=_numero_documento_bancario(d.nro_documento),
                monto=_to_decimal(d.monto_pagado_en_esta_nomina),
                glosa=(d.glosa or "").strip() or "Pago proveedores",
            )
        )

    template_path = get_template_path(root_path, TEMPLATE_PAGOS_PROV)
    wb = build_xlsx_from_template(
        template_path=template_path,
        template_kind="PAGOS_PROV",
        rows=rows,
        anio=int(nomina.periodo_anio),
        mes=int(nomina.periodo_mes),
        glosa=None,
    )
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()