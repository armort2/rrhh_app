# web/app/services/anticipos_builder.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import Trabajador, Obra, Cargo
from ..models import AnticipoNomina, AnticipoDetalle  # <- ajusta si tus clases están en models.py


def prev_period(anio: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return anio - 1, 12
    return anio, mes - 1


def get_or_create_nomina(*, anio: int, mes: int, centro_costo: str, user_id: int | None = None) -> AnticipoNomina:
    cc = (centro_costo or "").strip().upper()
    if not cc:
        raise ValueError("Centro de costo es obligatorio.")

    nomina = AnticipoNomina.query.filter_by(anio=anio, mes=mes, centro_costo=cc).first()
    if not nomina:
        nomina = AnticipoNomina(
            anio=anio,
            mes=mes,
            centro_costo=cc,
            estado="BORRADOR",
            origen="MANUAL",
            importado_por=user_id,
            importado_en=datetime.utcnow(),
        )
        db.session.add(nomina)
        db.session.flush()
    return nomina


def sync_detalles_con_trabajadores_cc(*, nomina: AnticipoNomina) -> dict[str, Any]:
    """
    Inserta AnticipoDetalle faltantes para todos los trabajadores del Centro de Costo.
    Etapa actual: incluye NO VIGENTES (no filtra por estado_trabajador).
    No borra ni pisa montos existentes.
    """
    cc = (nomina.centro_costo or "").strip().upper()

    # Trabajadores del CC (SIN filtrar vigencia)
    trabajadores_cc = (
        db.session.query(Trabajador, Obra)
        .join(Obra, Obra.id == Trabajador.obra_id)
        .filter(and_(Obra.centro_costo.isnot(None), Obra.centro_costo.ilike(cc)))
        .all()
    )

    # set de trabajador_id ya existentes en la nómina
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

        nombre_completo = " ".join(
            [p for p in [t.nombres, t.ap_paterno, (t.ap_materno or "")] if p]
        ).strip()

        # rut mostrado (si guardas rut+dv separados, construye)
        rut_show = None
        if getattr(t, "rut", None):
            if getattr(t, "dv", None):
                rut_show = f"{t.rut}-{t.dv}"
            else:
                rut_show = str(t.rut)

        d = AnticipoDetalle(
            nomina_id=nomina.id,
            trabajador_id=t.id,
            obra_id=obra.id if obra else None,
            rut=rut_show,
            nombre_completo=nombre_completo or None,
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


def get_detalles_con_referencia_mes_anterior(*, nomina_id: int) -> list[dict[str, Any]]:
    """
    Retorna filas para planilla:
    - detalle actual
    - tipo_trabajador, cargo
    - monto_mes_anterior (solo referencia)
    """
    nomina = AnticipoNomina.query.get_or_404(nomina_id)

    anio_prev, mes_prev = prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()

    PrevDet = aliased(AnticipoDetalle)

    q = (
        db.session.query(
            AnticipoDetalle,
            Trabajador.tipo_trabajador,
            Cargo.nombre.label("cargo_nombre"),
            PrevDet.monto.label("monto_prev"),
        )
        .join(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(Cargo, Cargo.id == Trabajador.cargo_id)
        .outerjoin(
            PrevDet,
            and_(
                nomina_prev is not None,
                PrevDet.nomina_id == (nomina_prev.id if nomina_prev else None),
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
            ),
        )
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    rows = []
    for det, tipo, cargo_nombre, monto_prev in q.all():
        rows.append({
            "d": det,
            "tipo_trabajador": (tipo or "SIN TIPO"),
            "cargo_nombre": (cargo_nombre or "-"),
            "monto_prev": float(monto_prev or 0),
        })

    # Orden recomendado para que el template agrupe bien
    rows.sort(key=lambda r: ((r["tipo_trabajador"] or "SIN TIPO").strip().upper(), (r["d"].nombre_completo or "")))
    return rows
