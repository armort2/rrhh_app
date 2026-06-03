# web/app/services/import_sueldos.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import re
from sqlalchemy import func

from ..extensions import db
from ..models import SueldoNomina, SueldoDetalle, Trabajador, Contrato, Obra

_RUT_RE = re.compile(r"^\d{1,9}-[0-9K]$")


def _is_valid_rut(rut: str | None) -> bool:
    if not rut:
        return False
    return bool(_RUT_RE.match(rut.strip().upper()))


def _rut_sin_puntos_con_guion(rut_raw: str | None) -> str | None:
    if rut_raw is None:
        return None

    # Si viene como float tipo 21708149.0, lo convertimos a 21708149
    if isinstance(rut_raw, float) and rut_raw.is_integer():
        rut_raw = str(int(rut_raw))

    s = str(rut_raw).strip().replace(" ", "").replace(".", "")
    if not s:
        return None

    if "-" in s:
        base, dv = s.split("-", 1)
        base_digits = "".join(ch for ch in base if ch.isdigit())
        dv = dv.strip().upper()
        if base_digits and dv:
            return f"{base_digits}-{dv}"
        return s

    base_digits = "".join(ch for ch in s if ch.isdigit())
    return base_digits or s


def _parse_amount(v: Any) -> float:
    try:
        if v is None:
            return 0.0

        if isinstance(v, float) and pd.isna(v):
            return 0.0

        if isinstance(v, (int, float)):
            return float(v)

        s = str(v).strip()
        if not s:
            return 0.0

        s = s.replace("$", "").replace(" ", "")

        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
            return float(s)

        if "," in s and "." not in s:
            s = s.replace(",", ".")
            return float(s)

        if "." in s and "," not in s:
            left, right = s.split(".", 1)
            if right.isdigit() and len(right) == 3 and left.replace(".", "").isdigit():
                s = s.replace(".", "")
                return float(s)
            return float(s)

        return float(s)

    except Exception:
        return 0.0


def import_sueldos_from_excel(
    *,
    filepath: str,
    anio: int,
    mes: int,
    empleador_id: int,
    obra_id: int,
    centro_costo: str,
    user_id: int,
    allow_replace: bool = False,
    allow_reimport: bool | None = None,
) -> dict:

    obra = Obra.query.get(obra_id)
    if not obra:
        raise ValueError("Obra no encontrada.")

    # Compatibilidad: si viene allow_reimport (route nuevo), que mande.
    # Si vienen ambos, gana allow_reimport por ser explícito.
    if allow_reimport is not None:
        allow_replace = bool(allow_reimport)

    # Período [inicio, fin)
    periodo_inicio = date(anio, mes, 1)
    periodo_fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)

    # 1) abrir/crear nómina
    nomina = (
        SueldoNomina.query
        .filter_by(anio=anio, mes=mes, centro_costo=centro_costo, empleador_id=empleador_id)
        .first()
    )

    if nomina:
        if nomina.estado == "VISADA":
            raise ValueError("La nómina está VISADA. No se puede reemplazar.")

        if allow_replace:
            # borra SOLO detalles de esta nómina
            SueldoDetalle.query.filter_by(nomina_id=nomina.id).delete(synchronize_session=False)
            db.session.flush()

            # refrescar trazabilidad
            nomina.origen_archivo = filepath
            nomina.origen = "IMPORTADO"
            nomina.importado_por = user_id
            nomina.importado_en = datetime.utcnow()
        else:
            # conservador: si existe y no permites replace, no “pisamos”
            existe = (
                db.session.query(func.count(SueldoDetalle.id))
                .filter(SueldoDetalle.nomina_id == nomina.id)
                .scalar()
                or 0
            )
            if existe > 0:
                raise ValueError(
                    "Ya existe una nómina para ese período/CC/empleador. Marca 'Reemplazar' si corresponde."
                )
    else:
        nomina = SueldoNomina(
            anio=anio,
            mes=mes,
            centro_costo=centro_costo,
            empleador_id=empleador_id,
            estado="BORRADOR",
            origen_archivo=filepath,
            origen="IMPORTADO",
            importado_por=user_id,
            importado_en=datetime.utcnow(),
        )
        db.session.add(nomina)
        db.session.flush()

    # 2) leer excel
    # A=0 rut, C=2 nombre, J=9 anticipo, K=10 líquido
    df = pd.read_excel(filepath, header=None)

    filas = 0
    ok = 0
    excluidos = 0

    for _, row in df.iterrows():
        rut_raw = row.iloc[0] if len(row) > 0 else None
        nombre_raw = row.iloc[2] if len(row) > 2 else None
        anticipo_raw = row.iloc[9] if len(row) > 9 else None
        liquido_raw = row.iloc[10] if len(row) > 10 else None

        # Normalizar NaN reales de pandas
        if pd.isna(rut_raw):
            continue  # SIN RUT -> no es trabajador

        rut = _rut_sin_puntos_con_guion(rut_raw)

        # Regla de oro: solo filas con RUT válido
        if not _is_valid_rut(rut):
            continue  # títulos, totales, textos -> fuera

        if pd.isna(nombre_raw):
            nombre_raw = None
        nombre = " ".join(str(nombre_raw or "").split()).strip() or None

        anticipo = _parse_amount(anticipo_raw)
        liquido = _parse_amount(liquido_raw)

        filas += 1

        estado_linea = "OK"
        obs = None

        if liquido <= 0:
            estado_linea = "LIQUIDO_CERO"
            obs = "Líquido <= 0"

        trabajador_id = None
        contrato_id = None
        obra_det_id = obra_id  # default: obra seleccionada

        # match trabajador
        t = None
        if rut and "-" in rut:
            base, dv = rut.split("-", 1)
            base_digits = "".join(ch for ch in base if ch.isdigit())
            dv = dv.strip().upper()

            t = (
                Trabajador.query
                .filter(func.replace(func.coalesce(Trabajador.rut, ""), ".", "") == base_digits)
                .filter(func.upper(func.coalesce(Trabajador.dv, "")) == dv)
                .first()
            )

        if not t:
            if estado_linea == "OK":
                estado_linea = "SIN_TRABAJADOR"
                obs = "No se encontró trabajador por RUT"
        else:
            trabajador_id = t.id

            # buscar contratos que cubran período y sean del empleador
            contratos_q = (
                Contrato.query
                .filter(Contrato.trabajador_id == t.id)
                .filter(Contrato.empleador_id == empleador_id)
                .filter(Contrato.fecha_inicio.isnot(None))
                .filter(Contrato.fecha_inicio < periodo_fin)
                .filter(func.coalesce(Contrato.fecha_termino, date(2999, 12, 31)) >= periodo_inicio)
            )

            contratos = contratos_q.order_by(Contrato.id.desc()).all()

            # si el contrato tiene obra_id, preferir el que calce con la obra seleccionada
            if contratos:
                contratos_misma_obra = [c for c in contratos if getattr(c, "obra_id", None) == obra_id]
                pick_pool = contratos_misma_obra or contratos

                if len(pick_pool) == 1:
                    c = pick_pool[0]
                    contrato_id = c.id
                    if getattr(c, "obra_id", None):
                        obra_det_id = c.obra_id
                else:
                    # ambiguo: elegimos el más nuevo pero dejamos rastro
                    c = pick_pool[0]
                    contrato_id = c.id
                    if estado_linea == "OK":
                        estado_linea = "AMBIGUO_CONTRATO"
                        obs = f"Múltiples contratos en período ({len(pick_pool)}). Se tomó el más reciente."
                    if getattr(c, "obra_id", None):
                        obra_det_id = c.obra_id
            else:
                if estado_linea == "OK":
                    estado_linea = "SIN_CONTRATO_EN_PERIODO"
                    obs = "No se encontró contrato del empleador en el período"

        d = SueldoDetalle(
            nomina_id=nomina.id,
            trabajador_id=trabajador_id,
            contrato_id=contrato_id,
            obra_id=obra_det_id,
            centro_costo=centro_costo,
            rut=rut,
            nombre_completo=nombre,
            nombre_obra=(obra.nombre or None),
            anticipo=anticipo if anticipo is not None else 0,
            liquido=liquido if liquido is not None else 0,
            estado_linea=estado_linea,
            observacion=obs,
        )
        db.session.add(d)

        if estado_linea == "OK":
            ok += 1
        else:
            excluidos += 1

    db.session.commit()

    return {
        "nomina_id": nomina.id,
        "periodo": f"{anio:04d}-{mes:02d}",
        "centro_costo": centro_costo,
        "obra_label": obra.nombre or f"Obra #{obra.id}",
        "stats": {
            "filas": filas,
            "ok": ok,
            "excluidos": excluidos,
        },
    }