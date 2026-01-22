# web/app/services/anticipos_reader.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from ..extensions import db
from ..models import AnticipoNomina, AnticipoDetalle, Trabajador, Cargo


@dataclass
class ResumenAnticiposQuincena:
    centro_costo: str
    anio: int
    mes: int
    nomina_id: int
    estado: str
    total_monto: Decimal
    subtotales_tipo: List[Dict[str, Any]]
    filas: List[Dict[str, Any]]


def _tipo_key_expr():
    return sa.func.upper(sa.func.trim(sa.func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO")))


def _tipo_priority_expr(tipo_key_expr):
    return sa.case(
        (tipo_key_expr == "JEFATURA U OTROS", 0),
        else_=1,
    )


def get_resumen_anticipos_para_quincena(
    centro_costo: str,
    anio: int,
    mes: int,
) -> Optional[ResumenAnticiposQuincena]:
    """
    Retorna resumen + filas de anticipos para el CC en un período (anio/mes),
    pero SOLO si existe nómina VISADA.
    Si no existe VISADA, retorna None (para que la UI no muestre nada).
    """

    cc = (centro_costo or "").strip().upper()
    if not cc or not anio or not mes:
        return None

    # 1) Buscar nómina VISADA (última por id, por si existe más de una por cualquier motivo)
    nomina = (
        AnticipoNomina.query.filter_by(centro_costo=cc, anio=int(anio), mes=int(mes))
        .filter(AnticipoNomina.estado == "VISADA")
        .order_by(AnticipoNomina.id.desc())
        .first()
    )
    if not nomina:
        return None

    # 2) Traer filas en el MISMO ORDEN del detalle de anticipos
    tipo_key = _tipo_key_expr()
    tipo_prio = _tipo_priority_expr(tipo_key)

    q = (
        db.session.query(
            AnticipoDetalle,
            Cargo.nombre.label("cargo_nombre"),
            Trabajador.tipo_trabajador.label("tipo_trabajador"),
            Trabajador.ap_paterno.label("ap_paterno"),
            Trabajador.ap_materno.label("ap_materno"),
            Trabajador.nombres.label("nombres"),
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    rows = (
        q.order_by(
            tipo_prio.asc(),
            tipo_key.asc(),
            sa.func.coalesce(Trabajador.ap_paterno, "").asc(),
            sa.func.coalesce(Trabajador.ap_materno, "").asc(),
            sa.func.coalesce(Trabajador.nombres, "").asc(),
            sa.func.coalesce(AnticipoDetalle.nombre_completo, "").asc(),
            AnticipoDetalle.id.asc(),
        )
        .all()
    )

    filas: List[Dict[str, Any]] = []
    total = Decimal("0.00")

    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        monto = Decimal(str(d.monto or 0))
        total += monto

        filas.append(
            {
                "id": d.id,
                "rut": getattr(d, "rut", None) or "-",
                "nombre": nombre_ordenado,
                "cargo": cargo_nombre or "-",
                "tipo": (tipo_trabajador or "SIN TIPO").strip(),
                "obra": getattr(d, "nombre_obra", None) or "-",
                "monto": monto,
                "observacion": getattr(d, "observacion", None) or None,
            }
        )

    # 3) Subtotales por tipo (como en anticipos)
    subtotales = (
        db.session.query(
            sa.func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").label("tipo"),
            sa.func.coalesce(sa.func.sum(AnticipoDetalle.monto), 0).label("total"),
            sa.func.count(AnticipoDetalle.id).label("cantidad"),
        )
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .group_by(sa.func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO"))
        .order_by(sa.func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").asc())
        .all()
    )

    subtotales_tipo = [
        {
            "tipo": (r.tipo or "SIN TIPO"),
            "total": Decimal(str(r.total or 0)),
            "cantidad": int(r.cantidad or 0),
        }
        for r in subtotales
    ]

    return ResumenAnticiposQuincena(
        centro_costo=cc,
        anio=int(anio),
        mes=int(mes),
        nomina_id=int(nomina.id),
        estado=str(nomina.estado),
        total_monto=total,
        subtotales_tipo=subtotales_tipo,
        filas=filas,
    )