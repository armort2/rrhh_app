# web/app/blueprints/desvinculaciones/routes.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required
import sqlalchemy as sa
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from ...extensions import db
from ...models import (
    CausalTermino,
    Contrato,
    Desvinculacion,
    Trabajador,
    DesvinculacionDocInputs,
    Inasistencia,
    Obra,
    VacacionMovimiento, Feriado,
)
from ...services.desvinculaciones_docs import build_carta_aviso_docx, build_finiquito_docx
from ...services.paths_nextcloud import get_nc_paths
from ...services.pdf_convert import convert_docx_to_pdf
from ...services.storage_nextcloud_fs import ensure_dir
from ...utils import parse_date, parse_int

from ...services.finiquitos_calc import calcular_resumen_finiquito

bp = Blueprint("desvinculaciones", __name__, url_prefix="/desvinculaciones")


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
    Define carpeta destino en Nextcloud FS usando el estándar corporativo:
    /<CENTRO_COSTO>/Laboral/Trabajadores/<Apellido Apellido Nombres>/DESVINCULACIONES/
    """
    c = desv.contrato
    t = desv.trabajador

    obra = getattr(c, "obra", None)
    centro_costo = (getattr(obra, "centro_costo", "") or "").strip() if obra else ""
    if not centro_costo:
        raise RuntimeError("No se pudo determinar el centro de costo (obras.centro_costo).")

    nc = get_nc_paths()
    return nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=t.nombres or "",
        ap_paterno=t.ap_paterno or "",
        ap_materno=t.ap_materno or "",
        tipo_doc="DESVINCULACIONES",
    )


def _get_contrato_vigente_actual(trabajador_id: int) -> Contrato | None:
    hoy = date.today()

    q = Contrato.query.filter_by(trabajador_id=trabajador_id, estado_contrato="VIGENTE")

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q = (
            q.filter(Contrato.fecha_inicio <= hoy)
            .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    return q.order_by(Contrato.fecha_inicio.desc().nullslast(), Contrato.id.desc()).first()

def _get_contratos_vigentes_desvinculables(trabajador_id: int) -> list[Contrato]:
    """
    Retorna contratos vigentes que pueden seleccionarse para iniciar una desvinculación.
    Orden:
    - más recientes primero por fecha_inicio
    - luego id desc
    """
    hoy = date.today()

    q = Contrato.query.filter_by(
        trabajador_id=trabajador_id,
        estado_contrato="VIGENTE",
    )

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q = (
            q.filter(Contrato.fecha_inicio <= hoy)
            .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    return (
        q.order_by(
            Contrato.fecha_inicio.desc().nullslast(),
            Contrato.id.desc(),
        )
        .all()
    )


def _get_contrato_vigente_by_id_para_trabajador(trabajador_id: int, contrato_id: int | None) -> Contrato | None:
    """
    Devuelve un contrato vigente específico del trabajador.
    Se usa cuando el usuario elige qué contrato desvincular.
    """
    if not contrato_id:
        return None

    hoy = date.today()

    q = Contrato.query.filter_by(
        id=contrato_id,
        trabajador_id=trabajador_id,
        estado_contrato="VIGENTE",
    )

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q = (
            q.filter(Contrato.fecha_inicio <= hoy)
            .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    return q.first()


def _get_otro_contrato_vigente(trabajador_id: int, excluir_contrato_id: int | None = None) -> Contrato | None:
    """
    Busca otro contrato vigente del trabajador, excluyendo el contrato indicado.
    Útil después de emitir una desvinculación.
    """
    hoy = date.today()

    q = Contrato.query.filter(
        Contrato.trabajador_id == trabajador_id,
        Contrato.estado_contrato == "VIGENTE",
    )

    if excluir_contrato_id:
        q = q.filter(Contrato.id != excluir_contrato_id)

    if hasattr(Contrato, "fecha_inicio") and hasattr(Contrato, "fecha_termino"):
        q = (
            q.filter(Contrato.fecha_inicio <= hoy)
            .filter(or_(Contrato.fecha_termino.is_(None), Contrato.fecha_termino >= hoy))
        )

    return (
        q.order_by(
            Contrato.fecha_inicio.desc().nullslast(),
            Contrato.id.desc(),
        )
        .first()
    )

def _redirect_back_or(endpoint: str, **kwargs):
    next_url = (request.args.get("next") or request.form.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(endpoint, **kwargs))


_MONEY_DIGITS_RE = re.compile(r"[^\d]")


def _parse_money_to_str(raw: str) -> str:
    """
    Normaliza montos:
    - '350000' -> '350.000'
    - '350.000' -> '350.000'
    - '' -> ''
    """
    s = (raw or "").strip()
    if not s:
        return ""
    digits = _MONEY_DIGITS_RE.sub("", s)
    if not digits:
        return ""
    n = int(digits)
    return f"{n:,}".replace(",", ".")

def _parse_json_dict(raw: str | None) -> dict:
    """
    Intenta parsear un JSON string y devuelve dict seguro.
    Si falla o no es dict, devuelve {}.
    """
    s = (raw or "").strip()
    if not s:
        return {}

    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _get_finiquito_inputs(desv: Desvinculacion) -> dict:
    meta = (desv.meta or {}) if hasattr(desv, "meta") else {}
    inputs = meta.get("finiquito_inputs") or {}
    return inputs if isinstance(inputs, dict) else {}


# --- helper: tiempo servido (años/meses/días) ---

def _days_in_month(y: int, m: int) -> int:
    # sin calendar para mantenerlo simple y estable
    # febrero:
    if m == 2:
        leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
        return 29 if leap else 28
    # 30 días:
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _diff_ymd(start: date, end: date) -> Tuple[int, int, int]:
    """
    Diferencia calendario entre fechas (end >= start):
    devuelve (años, meses, días) con "borrow" estilo humano.
    """
    if end < start:
        start, end = end, start

    y = end.year - start.year
    m = end.month - start.month
    d = end.day - start.day

    if d < 0:
        # borrow 1 mes desde end
        m -= 1
        prev_month = end.month - 1
        prev_year = end.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        d += _days_in_month(prev_year, prev_month)

    if m < 0:
        y -= 1
        m += 12

    if y < 0:
        y = 0
    if m < 0:
        m = 0
    if d < 0:
        d = 0

    return y, m, d


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _fmt_tiempo_servido(anios: int, meses: int, dias: int) -> str:
    # Formato corporativo: "X año(s), X mes(es) y X día(s)"
    parts = []
    if anios:
        parts.append(f"{anios} {_plural(anios, 'año', 'años')}")
    if meses:
        parts.append(f"{meses} {_plural(meses, 'mes', 'meses')}")
    if dias or not parts:
        parts.append(f"{dias} {_plural(dias, 'día', 'días')}")

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} y {parts[1]}"
    return ", ".join(parts[:-1]) + " y " + parts[-1]


def _compute_tiempo_servido(desv: Desvinculacion) -> dict:
    """
    Devuelve:
      - contrato_fecha_inicio (date|None)
      - tiempo_servido_txt (str)
      - tiempo_servido_anios/meses/dias (int)
    Usa fecha término de desvinculación si existe; si no, usa hoy.
    """
    c = desv.contrato
    fecha_inicio = getattr(c, "fecha_inicio", None)
    if not fecha_inicio:
        return {
            "contrato_fecha_inicio": None,
            "tiempo_servido_txt": "",
            "tiempo_servido_anios": 0,
            "tiempo_servido_meses": 0,
            "tiempo_servido_dias": 0,
        }

    fecha_fin = desv.fecha_termino or date.today()
    y, m, d = _diff_ymd(fecha_inicio, fecha_fin)

    return {
        "contrato_fecha_inicio": fecha_inicio,
        "tiempo_servido_txt": _fmt_tiempo_servido(y, m, d),
        "tiempo_servido_anios": y,
        "tiempo_servido_meses": m,
        "tiempo_servido_dias": d,
    }


def _norm_doc_tipo(doc_tipo: str) -> str:
    return (doc_tipo or "").strip().upper()


def _get_doc_inputs(desv_id: int, doc_tipo: str) -> dict:
    doc_tipo = _norm_doc_tipo(doc_tipo)
    row = (
        DesvinculacionDocInputs.query
        .filter_by(desvinculacion_id=desv_id, doc_tipo=doc_tipo)
        .first()
    )
    if not row or not isinstance(row.inputs, dict):
        return {}
    return row.inputs


def _upsert_doc_inputs(desv: Desvinculacion, doc_tipo: str, inputs: dict) -> DesvinculacionDocInputs:
    """
    Upsert seguro (Opción A):
      - Busca por (desvinculacion_id, doc_tipo)
      - Actualiza si existe; crea si no existe.
    OJO: No hace commit; solo add/flush. El commit lo maneja el caller.
    """
    doc_tipo = _norm_doc_tipo(doc_tipo)
    if not doc_tipo:
        raise ValueError("doc_tipo vacío en _upsert_doc_inputs")

    payload = inputs if isinstance(inputs, dict) else {}

    row = (
        DesvinculacionDocInputs.query
        .filter_by(desvinculacion_id=desv.id, doc_tipo=doc_tipo)
        .first()
    )

    if row is None:
        row = DesvinculacionDocInputs(
            desvinculacion_id=desv.id,
            doc_tipo=doc_tipo,
            inputs=payload,
        )
        db.session.add(row)
    else:
        row.inputs = payload

    # Flush temprano: si hay problema con constraint/DB, explota aquí (no al final).
    db.session.flush()
    return row

def _commit_or_rollback(context: str) -> None:
    """
    Commit con logging.
    Si falla, rollback y deja trazabilidad en logs.
    """
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.exception("IntegrityError en commit (%s)", context)
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error inesperado en commit (%s)", context)
        raise

def _save_doc_inputs(desv: Desvinculacion, doc_tipo: str, inputs: dict, audit_key: str, extra_audit: dict | None = None) -> None:
    """
    Guarda inputs (upsert) + auditoría (meta) y comitea.
    Ideal para guardar el formulario ANTES de generar archivos.
    """
    _upsert_doc_inputs(desv, doc_tipo, inputs)

    audit_payload = {"doc_tipo": _norm_doc_tipo(doc_tipo), "inputs": inputs}
    if extra_audit:
        audit_payload.update(extra_audit)

    _push_meta(desv, audit_key, audit_payload)

    _commit_or_rollback(f"save_doc_inputs {doc_tipo} desv={desv.id}")

# ============================================================
# ✅ NUEVO: Presets Art. 161 (Necesidades de la empresa)
# ============================================================

# Keys estables (persistibles); labels para UI; text para insertar.
_CAUSAL_8_PRESETS: list[dict[str, str]] = [
    {
        "key": "REESTRUCTURACION_OPERATIVA",
        "label": "Reestructuración interna / reorganización operativa",
        "text": (
            "un proceso de reestructuración interna y optimización de su organización operativa, "
            "orientado a adecuar la dotación de personal a los actuales requerimientos productivos y de gestión de la obra, "
            "lo que ha implicado la supresión y reorganización de determinadas funciones, entre ellas aquellas desempeñadas por el trabajador"
        ),
    },
    {
        "key": "AVANCE_OBRA_AJUSTE_DOTACION",
        "label": "Avance de obra / ajuste de dotación por fase",
        "text": (
            "un proceso de ajuste de dotación derivado del estado de avance de la obra, "
            "el cual ha implicado una disminución progresiva de los requerimientos de personal en determinadas áreas, "
            "haciendo innecesaria la mantención de algunas funciones, entre ellas aquellas desempeñadas por el trabajador"
        ),
    },
    {
        "key": "CAMBIO_ETAPA_REORGANIZACION",
        "label": "Cambio de etapa constructiva / reorganización de procesos",
        "text": (
            "la adecuación de la dotación de personal como consecuencia del cambio de etapas en la ejecución de la obra, "
            "lo que ha significado una reorganización de los procesos productivos y una reducción de funciones requeridas en esta fase del proyecto, "
            "entre ellas aquellas desempeñadas por el trabajador"
        ),
    },
]


def _preset_text_by_key(key: str | None) -> str:
    k = (key or "").strip().upper()
    if not k:
        return ""
    for p in _CAUSAL_8_PRESETS:
        if (p.get("key") or "").upper() == k:
            return (p.get("text") or "").strip()
    return ""


# ============================================================
# ✅ NUEVO: Autofill CAUSAL 7 desde Inasistencias
# ============================================================

# ✅ CORREGIDO: en DB se guarda el CÓDIGO, no el label
_MOTIVO_AUSENCIA_INJUST = "AUSENCIA_INJUSTIFICADA"

_MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _month_range(ref: date) -> tuple[date, date]:
    """
    Rango mensual [desde, hasta) (hasta exclusivo).
    """
    desde = date(ref.year, ref.month, 1)
    if ref.month == 12:
        hasta = date(ref.year + 1, 1, 1)
    else:
        hasta = date(ref.year, ref.month + 1, 1)
    return desde, hasta


def _get_ausencias_injustificadas(trabajador_id: int, mes_ref: date) -> list[Inasistencia]:
    """
    Trae inasistencias DIA del mes (código AUSENCIA_INJUSTIFICADA).
    """
    start, end = _month_range(mes_ref)
    q = (
        Inasistencia.query
        .filter(Inasistencia.trabajador_id == trabajador_id)
        .filter(Inasistencia.fecha >= start, Inasistencia.fecha < end)
        .filter(Inasistencia.tipo == "DIA")
        .filter(Inasistencia.motivo == _MOTIVO_AUSENCIA_INJUST)
        .order_by(Inasistencia.fecha.asc(), Inasistencia.id.asc())
    )
    return q.all()


def _suggest_frase_dias(fechas: list[date]) -> str | None:
    """
    Reglas (prioridad):
      1) 3+ días -> "tres días en el mes"
      2) 2 consecutivos -> "dos días seguidos en el mes"
      3) 2 lunes -> "dos días lunes en el mes"
    """
    fechas_u = sorted(set(fechas))
    n = len(fechas_u)

    # ✅ Prioridad alta
    if n >= 3:
        return "tres días en el mes"

    if n >= 2:
        # 2 días seguidos
        for i in range(n - 1):
            if (fechas_u[i + 1] - fechas_u[i]).days == 1:
                return "dos días seguidos en el mes"

        # 2 lunes
        lunes = sum(1 for f in fechas_u if f.weekday() == 0)
        if lunes >= 2:
            return "dos días lunes en el mes"

    return None


def _format_detalle_dias(fechas: list[date], mes_ref: date) -> str:
    fechas_u = sorted(set(fechas))
    if not fechas_u:
        return ""

    dias = [f"{d.day:02d}" for d in fechas_u]
    mes = _MESES_ES.get(mes_ref.month, "")
    anio = mes_ref.year

    if len(dias) == 1:
        dias_txt = dias[0]
    elif len(dias) == 2:
        dias_txt = f"{dias[0]} y {dias[1]}"
    else:
        dias_txt = ", ".join(dias[:-1]) + f" y {dias[-1]}"

    return f"los días {dias_txt} de {mes} de {anio}"


def _causal_calza_autofill_ausencias(desv: Desvinculacion) -> bool:
    """
    Gate conservador:
    - Si causal_id == 7 (por convención interna de tus tags "CAUSAL_7_*"), o
    - Si en causal_finiquito aparece algo tipo "160" y "3" (fallback tolerante).
    """
    try:
        if int(desv.causal_id or 0) == 7:
            return True
    except Exception:
        pass

    c = getattr(desv, "causal", None)
    txt = ""
    if c is not None:
        txt = " ".join([
            str(getattr(c, "causal_resumida", "") or ""),
            str(getattr(c, "causal_finiquito", "") or ""),
        ]).upper()

    # fallback: menciona 160 y N°3 (o "3")
    if "160" in txt and "3" in txt:
        return True

    # último fallback: si menciona "INASIST" o "AUSENCIA"
    if "INASIST" in txt or "AUSENCIA" in txt:
        return True

    return False


def _autofill_causal_7_from_inasistencias(desv: Desvinculacion, defaults: dict) -> dict:
    """
    Si corresponde, completa defaults (solo si están vacíos) con:
      - CAUSAL_7_DETALLE_DIAS
      - CAUSAL_7_FRASE_DIAS
    Además guarda en DesvinculacionDocInputs(CARTA_AVISO) para re-edición.
    """
    if not desv.fecha_termino:
        return defaults

    if not _causal_calza_autofill_ausencias(desv):
        return defaults

    # Si el usuario ya escribió algo, no lo pisamos.
    if (defaults.get("CAUSAL_7_DETALLE_DIAS") or "").strip() and (defaults.get("CAUSAL_7_FRASE_DIAS") or "").strip():
        return defaults

    mes_ref = desv.fecha_termino
    inas = _get_ausencias_injustificadas(desv.trabajador_id, mes_ref)
    fechas = [i.fecha for i in inas if i.fecha]

    if not fechas:
        # nada que sugerir
        return defaults

    detalle = _format_detalle_dias(fechas, mes_ref)
    frase = _suggest_frase_dias(fechas) or ""

    changed = False

    if not (defaults.get("CAUSAL_7_DETALLE_DIAS") or "").strip():
        defaults["CAUSAL_7_DETALLE_DIAS"] = detalle
        changed = True

    if not (defaults.get("CAUSAL_7_FRASE_DIAS") or "").strip():
        defaults["CAUSAL_7_FRASE_DIAS"] = frase
        changed = True

    if changed:
        # Persistir defaults sugeridos en tabla (sin sobreescribir otras llaves)
        carta_last = _get_doc_inputs(desv.id, "CARTA_AVISO") or {}
        payload = dict(carta_last)

        payload.setdefault("CAUSAL_7_DETALLE_DIAS", defaults.get("CAUSAL_7_DETALLE_DIAS", ""))
        payload.setdefault("CAUSAL_7_FRASE_DIAS", defaults.get("CAUSAL_7_FRASE_DIAS", ""))

        payload["SUGERIDO_DESDE_INASISTENCIAS"] = True
        payload["INASISTENCIAS_IDS"] = [i.id for i in inas]
        payload["INASISTENCIAS_COUNT"] = len(inas)
        payload["INASISTENCIAS_RESUMEN"] = f"{len(set(fechas))} día(s) en el mes"

        _upsert_doc_inputs(desv, "CARTA_AVISO", payload)

        _push_meta(
            desv,
            "carta_autofill_causal_7",
            {
                "mes_ref": mes_ref.isoformat(),
                "motivo": _MOTIVO_AUSENCIA_INJUST,
                "inasistencias_ids": [i.id for i in inas],
                "detalle": detalle,
                "frase": frase,
            },
        )

        db.session.commit()

    return defaults


# ---------------------------
# Listado
# ---------------------------

@bp.get("/")
@login_required
def listado():
    """
    Listado con filtros:
    - estado: BORRADOR / EMITIDA / ANULADA / (vacío = todos)
    - desde/hasta por fecha_termino
    - mes (YYYY-MM) por fecha_termino
    - obra_id (Obra) por Desvinculacion.obra_id o Contrato.obra_id (compat)
    - q: nombre/apellidos/rut/dv (tokens AND)
    """
    estado = (request.args.get("estado") or "").strip().upper()
    desde = parse_date(request.args.get("desde"))
    hasta = parse_date(request.args.get("hasta"))
    q_busqueda = (request.args.get("q") or "").strip()

    # ✅ nuevos filtros
    obra_id = parse_int(request.args.get("obra_id"))
    mes = (request.args.get("mes") or "").strip()  # "YYYY-MM"

    query = (
        Desvinculacion.query
        .join(Trabajador, Trabajador.id == Desvinculacion.trabajador_id)
        .join(CausalTermino, CausalTermino.id == Desvinculacion.causal_id)
        .outerjoin(Contrato, Contrato.id == Desvinculacion.contrato_id)  # ✅ filtro obra vía contrato
    )

    # -------------------
    # Filtro estado
    # -------------------
    if estado in {"BORRADOR", "EMITIDA", "ANULADA"}:
        query = query.filter(Desvinculacion.estado == estado)

    # -------------------
    # Filtro desde/hasta
    # -------------------
    if desde:
        query = query.filter(Desvinculacion.fecha_termino >= desde)
    if hasta:
        query = query.filter(Desvinculacion.fecha_termino <= hasta)

    # -------------------
    # ✅ Filtro mes término (YYYY-MM)
    # -------------------
    filtro_mes = ""
    filtro_mes_year = ""
    filtro_mes_month = ""
    if mes:
        try:
            y_s, m_s = mes.split("-", 1)
            y = int(y_s)
            m = int(m_s)
            if 1 <= m <= 12:
                start = date(y, m, 1)
                end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

                query = query.filter(Desvinculacion.fecha_termino >= start)
                query = query.filter(Desvinculacion.fecha_termino < end)

                filtro_mes = f"{y:04d}-{m:02d}"
                filtro_mes_year = f"{y:04d}"
                filtro_mes_month = f"{m:02d}"
        except Exception:
            filtro_mes = ""
            filtro_mes_year = ""
            filtro_mes_month = ""

    # -------------------
    # ✅ Filtro obra/centro de costo
    # - Compat: Desvinculacion.obra_id o Contrato.obra_id
    # -------------------
    filtro_obra_id = obra_id or ""
    if obra_id:
        query = query.filter(
            or_(
                Desvinculacion.obra_id == obra_id,
                Contrato.obra_id == obra_id,
            )
        )

    # -------------------
    # Filtro búsqueda q
    # -------------------
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

        if rut_digits:
            query = query.filter(Trabajador.rut.ilike(f"%{rut_digits}%"))
        if dv:
            query = query.filter(Trabajador.dv.ilike(f"%{dv}%"))

    # =========================================================
    # ✅ KPI (sobre la query filtrada, sin limit/order)
    # =========================================================
    # Subquery liviana (id + estado) para contar por estado sin duplicar joins
    q_kpi = query.with_entities(
        Desvinculacion.id.label("id"),
        Desvinculacion.estado.label("estado"),
    ).subquery()

    kpi_row = db.session.query(
        func.count(q_kpi.c.id).label("total"),
        func.sum(sa.case((q_kpi.c.estado == "EMITIDA", 1), else_=0)).label("emitida"),
        func.sum(sa.case((q_kpi.c.estado == "BORRADOR", 1), else_=0)).label("borrador"),
        func.sum(sa.case((q_kpi.c.estado == "ANULADA", 1), else_=0)).label("anulada"),
    ).one()

    kpi = {
        "total": int(kpi_row.total or 0),
        "emitida": int(kpi_row.emitida or 0),
        "borrador": int(kpi_row.borrador or 0),
        "anulada": int(kpi_row.anulada or 0),
    }

    # =========================================================
    # ✅ Data del listado (con límite por ahora)
    # =========================================================
    desvinculaciones = query.order_by(Desvinculacion.id.desc()).limit(200).all()

    # =========================================================
    # ✅ lista de obras para el select (centro_costo + nombre)
    # =========================================================
    obras = (
        Obra.query
        .order_by(Obra.centro_costo.asc().nullslast(), Obra.nombre.asc(), Obra.id.asc())
        .all()
    )

    # =========================================================
    # ✅ years para selector de año (tomados desde fechas de término existentes)
    # =========================================================
    years_raw = (
        db.session.query(func.extract("year", Desvinculacion.fecha_termino).label("y"))
        .filter(Desvinculacion.fecha_termino.isnot(None))
        .distinct()
        .order_by(sa.desc("y"))
        .all()
    )
    years = [int(r.y) for r in years_raw if r.y is not None]

    # asegurar año actual para UX (aunque no haya registros aún)
    hoy_y = date.today().year
    if hoy_y not in years:
        years = [hoy_y] + years

    # si no hay filtro, selecciona año actual y mes vacío (el template deja "Mes" seleccionado)
    if not filtro_mes_year:
        filtro_mes_year = str(hoy_y)

    # =========================================================
    # ✅ Totales a pago (FINIQUITO_TOTAL_PAGO) para control
    # - Fuente preferente: DesvinculacionDocInputs (doc_tipo=FINIQUITO)
    # - Fallback: desv.meta["finiquito_inputs"]
    # - Sin N+1: traemos todo en una sola consulta por IDs del listado
    # =========================================================
    def _money_to_int_any(raw: str | None) -> int:
        s = (raw or "").strip()
        if not s:
            return 0
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0

    def _fmt_clp(n: int) -> str:
        return f"{n:,}".replace(",", ".")

    ids_listado = [d.id for d in desvinculaciones] if desvinculaciones else []

    pagos_map: dict[int, dict] = {}
    total_pago_listado = 0
    total_pago_emitidas = 0

    if ids_listado:
        # 1) inputs desde tabla (preferente)
        inputs_rows = (
            DesvinculacionDocInputs.query
            .filter(DesvinculacionDocInputs.desvinculacion_id.in_(ids_listado))
            .filter(DesvinculacionDocInputs.doc_tipo == "FINIQUITO")
            .all()
        )

        inputs_by_id: dict[int, dict] = {}
        for r in inputs_rows:
            if isinstance(r.inputs, dict):
                inputs_by_id[r.desvinculacion_id] = r.inputs

        # 2) armar map final por cada desvinculación del listado (con fallback meta)
        for d in desvinculaciones:
            inputs = inputs_by_id.get(d.id)
            if not isinstance(inputs, dict):
                meta = (d.meta or {}) if hasattr(d, "meta") else {}
                inputs = meta.get("finiquito_inputs") if isinstance(meta.get("finiquito_inputs"), dict) else {}

            total_pago_raw = (inputs.get("FINIQUITO_TOTAL_PAGO") or "").strip() if isinstance(inputs, dict) else ""
            total_pago_i = _money_to_int_any(total_pago_raw)

            # Guardamos tanto int como fmt para UI
            pagos_map[d.id] = {
                "raw": total_pago_raw,
                "int": total_pago_i,
                "fmt": _fmt_clp(total_pago_i) if total_pago_i else "",
                "has": bool(total_pago_i),
            }

            total_pago_listado += total_pago_i
            if (d.estado or "").upper() == "EMITIDA":
                total_pago_emitidas += total_pago_i

    # Inyectamos a KPI (además de contadores)
    kpi["total_pago_listado"] = _fmt_clp(total_pago_listado)
    kpi["total_pago_emitidas"] = _fmt_clp(total_pago_emitidas)

    # =========================================================
    # ✅ Control Premium: Pago de finiquito (meta["pago_finiquito"])
    # Estructura esperada en meta:
    #   meta["pago_finiquito"] = {
    #       "estado": "PAGADO" | "PENDIENTE",
    #       "fecha_pago": "YYYY-MM-DD" o "DD-MM-YYYY" (lo normalizamos),
    #       "medio": "Transferencia" | "Efectivo" | "Cheque" | "Otro",
    #       "obs": "texto libre"
    #   }
    # =========================================================
    def _norm_pago_estado(s: str | None) -> str:
        s = (s or "").strip().upper()
        if s in {"PAGADO", "PENDIENTE"}:
            return s
        return ""

    def _fmt_fecha_pago(raw: str | None) -> str:
        """
        Devuelve 'dd-mm-YYYY' o '' si no hay.
        Acepta: YYYY-MM-DD o dd-mm-YYYY (también tolera '/')
        """
        s = (raw or "").strip()
        if not s:
            return ""
        s = s.replace("/", "-")

        # YYYY-MM-DD
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                dt = datetime.strptime(s, "%Y-%m-%d").date()
                return dt.strftime("%d-%m-%Y")
        except Exception:
            pass

        # dd-mm-YYYY
        try:
            if re.fullmatch(r"\d{2}-\d{2}-\d{4}", s):
                dt = datetime.strptime(s, "%d-%m-%Y").date()
                return dt.strftime("%d-%m-%Y")
        except Exception:
            pass

        return ""  # conservador: si no calza, preferimos vacío

    pago_map: dict[int, dict] = {}

    kpi_pagos = {
        "pagados": 0,
        "pendientes": 0,
        "monto_pagado": 0,
        "monto_pendiente": 0,
    }

    for d in desvinculaciones:
        meta = (d.meta or {}) if hasattr(d, "meta") else {}
        pmeta = meta.get("pago_finiquito") if isinstance(meta.get("pago_finiquito"), dict) else {}

        estado_pago = _norm_pago_estado(pmeta.get("estado"))
        fecha_pago = _fmt_fecha_pago(pmeta.get("fecha_pago"))
        medio_pago = (pmeta.get("medio") or "").strip()
        obs_pago = (pmeta.get("obs") or "").strip()

        pago_map[d.id] = {
            "estado": estado_pago,
            "fecha_pago": fecha_pago,
            "medio": medio_pago,
            "obs": obs_pago,
        }

        # KPIs premium (si quieres mostrarlos)
        monto_i = (pagos_map.get(d.id, {}) or {}).get("int", 0)  # monto finiquito del map actual

        if estado_pago == "PAGADO":
            kpi_pagos["pagados"] += 1
            kpi_pagos["monto_pagado"] += int(monto_i or 0)
        elif estado_pago == "PENDIENTE":
            kpi_pagos["pendientes"] += 1
            kpi_pagos["monto_pendiente"] += int(monto_i or 0)

    # formatear montos KPI premium para UI
    kpi_pagos["monto_pagado"] = _fmt_clp(int(kpi_pagos["monto_pagado"] or 0))
    kpi_pagos["monto_pendiente"] = _fmt_clp(int(kpi_pagos["monto_pendiente"] or 0))



    return render_template(
        "desvinculaciones/desvinculaciones_listado.html",
        desvinculaciones=desvinculaciones,

        q=q_busqueda,
        filtro_estado=estado,
        filtro_desde=desde,
        filtro_hasta=hasta,

        # filtros nuevos
        filtro_obra_id=filtro_obra_id,
        filtro_mes=filtro_mes,
        filtro_mes_year=filtro_mes_year,
        filtro_mes_month=filtro_mes_month,
        obras=obras,

        # KPI + years para el picker
        kpi=kpi,
        years=years,

        pagos_map=pagos_map,
        total_pago_listado=kpi.get("total_pago_listado", "0"),
        total_pago_emitidas=kpi.get("total_pago_emitidas", "0"),

        pago_map=pago_map,
        kpi_pagos=kpi_pagos,


    )


# ---------------------------
# Crear
# ---------------------------

@bp.get("/trabajador/<int:trabajador_id>/nueva")
@login_required
def nueva_desvinculacion(trabajador_id: int):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    contratos_vigentes = _get_contratos_vigentes_desvinculables(trabajador.id)
    if not contratos_vigentes:
        flash("Este trabajador no tiene contrato vigente. No se puede iniciar una desvinculación.", "error")
        return redirect(url_for("trabajadores.detalle_trabajador", trabajador_id=trabajador.id))

    contrato_id_sel = parse_int(request.args.get("contrato_id"))
    contrato_seleccionado = None

    if contrato_id_sel:
        contrato_seleccionado = _get_contrato_vigente_by_id_para_trabajador(trabajador.id, contrato_id_sel)

    if not contrato_seleccionado:
        contrato_seleccionado = contratos_vigentes[0]

    causales = CausalTermino.query.filter_by(activo=True).order_by(CausalTermino.id.asc()).all()

    return render_template(
        "desvinculaciones/desvinculacion_nueva.html",
        trabajador=trabajador,
        contrato=contrato_seleccionado,
        contratos_vigentes=contratos_vigentes,
        causales=causales,
    )


@bp.post("/trabajador/<int:trabajador_id>/crear")
@login_required
def crear_desvinculacion(trabajador_id: int):
    trabajador = Trabajador.query.get_or_404(trabajador_id)

    contrato_id = parse_int(request.form.get("contrato_id"))
    contrato_vigente = _get_contrato_vigente_by_id_para_trabajador(trabajador.id, contrato_id)

    if not contrato_vigente:
        flash("Debes seleccionar un contrato vigente válido para crear la desvinculación.", "error")
        return redirect(url_for("desvinculaciones.nueva_desvinculacion", trabajador_id=trabajador.id))

    causal_id = parse_int(request.form.get("causal_id"))
    fecha_termino = parse_date(request.form.get("fecha_termino"))
    fecha_aviso = parse_date(request.form.get("fecha_aviso"))
    motivo_detalle = (request.form.get("motivo_detalle") or "").strip() or None

    if not causal_id:
        flash("Debes seleccionar una causal de término.", "error")
        return redirect(
            url_for(
                "desvinculaciones.nueva_desvinculacion",
                trabajador_id=trabajador.id,
                contrato_id=contrato_vigente.id,
            )
        )

    causal = CausalTermino.query.get(causal_id)
    if not causal or not getattr(causal, "activo", False):
        flash("La causal seleccionada no es válida o está inactiva.", "error")
        return redirect(
            url_for(
                "desvinculaciones.nueva_desvinculacion",
                trabajador_id=trabajador.id,
                contrato_id=contrato_vigente.id,
            )
        )

    if not fecha_termino:
        flash("Debes indicar la fecha de término.", "error")
        return redirect(
            url_for(
                "desvinculaciones.nueva_desvinculacion",
                trabajador_id=trabajador.id,
                contrato_id=contrato_vigente.id,
            )
        )

    if fecha_aviso and fecha_aviso > fecha_termino:
        flash("La fecha de aviso no puede ser posterior a la fecha de término.", "error")
        return redirect(
            url_for(
                "desvinculaciones.nueva_desvinculacion",
                trabajador_id=trabajador.id,
                contrato_id=contrato_vigente.id,
            )
        )

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

    _push_meta(
        desv,
        "creacion",
        {
            "estado": "BORRADOR",
            "contrato_id": contrato_vigente.id,
        },
    )

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

    extra = _compute_tiempo_servido(desv)

    contrato_fecha_inicio_fmt = (
        extra["contrato_fecha_inicio"].strftime("%d-%m-%Y")
        if extra["contrato_fecha_inicio"]
        else ""
    )

    tiempo_servido_fmt = extra["tiempo_servido_txt"] or ""

    tiempo_servido_hint = (
        "Referencial para gestión. Para carta por “Necesidades de la empresa” "
        "se calculará con precisión calendario."
        if tiempo_servido_fmt
        else ""
    )

    next_url = request.url

    meta = dict(desv.meta or {})
    pmeta = meta.get("pago_finiquito") if isinstance(meta.get("pago_finiquito"), dict) else {}

    def _fmt_fecha_ddmmyyyy(iso: str | None) -> str:
        s = (iso or "").strip()
        if not s:
            return ""
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().strftime("%d-%m-%Y")
        except Exception:
            return ""

    pago_finiquito = {
        "estado": (pmeta.get("estado") or "").strip().upper(),
        "fecha_pago_iso": (pmeta.get("fecha_pago") or "").strip(),
        "fecha_pago_fmt": _fmt_fecha_ddmmyyyy(pmeta.get("fecha_pago")),
        "medio": (pmeta.get("medio") or "").strip(),
        "obs": (pmeta.get("obs") or "").strip(),
    }

    return render_template(
        "desvinculaciones/desvinculacion_detalle.html",
        desv=desv,
        contrato_fecha_inicio_fmt=contrato_fecha_inicio_fmt,
        tiempo_servido_fmt=tiempo_servido_fmt,
        tiempo_servido_hint=tiempo_servido_hint,
        next_url=next_url,
        pago_finiquito=pago_finiquito,
    )


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

    causales = CausalTermino.query.filter_by(activo=True).order_by(CausalTermino.id.asc()).all()

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

    if hasattr(contrato, "estado_contrato"):
        contrato.estado_contrato = "TERMINADO"

    if hasattr(contrato, "causal_termino"):
        contrato.causal_termino = desv.causal.causal_finiquito

    if hasattr(contrato, "fecha_finiquito"):
        contrato.fecha_finiquito = desv.fecha_termino

    # En desvinculación, el contrato terminado debe quedar con fecha_termino = fecha de desvinculación
    if hasattr(contrato, "fecha_termino"):
        contrato.fecha_termino = desv.fecha_termino

    desv.estado = "EMITIDA"
    _push_meta(
        desv,
        "emision",
        {
            "estado": "EMITIDA",
            "contrato_id": contrato.id,
        },
    )

    # Revisar si queda otro contrato vigente del trabajador
    otro_vigente = _get_otro_contrato_vigente(
        trabajador_id=trabajador.id,
        excluir_contrato_id=contrato.id,
    )

    if otro_vigente:
        # El trabajador sigue vigente porque aún tiene otro contrato activo
        if hasattr(trabajador, "estado_trabajador"):
            trabajador.estado_trabajador = "VIGENTE"

        if hasattr(trabajador, "fecha_egreso_empresa"):
            trabajador.fecha_egreso_empresa = None

        # Re-sincronizamos obra/cargo "actuales" con el otro contrato vigente
        if hasattr(trabajador, "obra_id"):
            trabajador.obra_id = getattr(otro_vigente, "obra_id", None)

        if hasattr(trabajador, "cargo_id"):
            trabajador.cargo_id = getattr(otro_vigente, "cargo_id", None)

        flash(
            f"Desvinculación emitida. Se terminó el contrato #{contrato.id}, "
            f"pero el trabajador mantiene otro contrato vigente (#{otro_vigente.id}).",
            "success",
        )
    else:
        # Ya no quedan contratos vigentes: el trabajador sale efectivamente de la empresa
        if hasattr(trabajador, "estado_trabajador"):
            trabajador.estado_trabajador = "NO_VIGENTE"

        if hasattr(trabajador, "fecha_egreso_empresa"):
            trabajador.fecha_egreso_empresa = desv.fecha_termino

        flash("Desvinculación emitida. Contrato y trabajador actualizados.", "success")

    db.session.commit()
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# ---------------------------
# Documentos
# ---------------------------

@bp.route("/<int:desvinculacion_id>/generar-carta", methods=["GET", "POST"])
@login_required
def generar_carta(desvinculacion_id: int):
    """
    Flujo:
    - GET  -> muestra formulario para carta aviso (formato + campos extra)
    - POST -> genera DOCX/PDF/AMBOS, guarda inputs (tabla), y persiste ruta.
    """
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado not in {"BORRADOR", "EMITIDA"}:
        flash("Solo puedes generar documentos en BORRADOR o EMITIDA.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    # info contrato (para mostrar en template)
    extra = _compute_tiempo_servido(desv)
    contrato_fecha_inicio_fmt = (
        extra["contrato_fecha_inicio"].strftime("%d-%m-%Y")
        if extra["contrato_fecha_inicio"]
        else ""
    )
    tiempo_servido_fmt = extra["tiempo_servido_txt"] or ""
    tiempo_servido_hint = (
        "Referencial para gestión. Para carta por “Necesidades de la empresa” "
        "se calculará con precisión calendario."
        if tiempo_servido_fmt
        else ""
    )

    # ✅ NUEVO (suave): warning para Art. 159 N°4 (vencimiento del plazo)
    warning_venc_plazo = ""
    try:
        if int(getattr(desv, "causal_id", 0) or 0) == 4:
            f_contrato = getattr(desv.contrato, "fecha_termino", None)
            f_desv = getattr(desv, "fecha_termino", None)

            if not f_contrato:
                warning_venc_plazo = (
                    "El contrato no tiene fecha de término registrada. "
                    "Esta carta (Art. 159 N°4) se basa en el vencimiento del plazo convenido."
                )
            elif f_desv and f_contrato != f_desv:
                warning_venc_plazo = (
                    "La fecha de término del contrato no coincide con la fecha de término de la desvinculación. "
                    "Revisa antes de generar/entregar la carta."
                )
    except Exception:
        # No interrumpimos el flujo por una validación de UI
        warning_venc_plazo = ""

    # Defaults base:
    fin_last = _get_doc_inputs(desv.id, "FINIQUITO")
    carta_last = _get_doc_inputs(desv.id, "CARTA_AVISO")

    meta = (desv.meta or {}) if hasattr(desv, "meta") else {}
    fin_meta = meta.get("finiquito_inputs") if isinstance(meta.get("finiquito_inputs"), dict) else {}

    # Mezcla: meta finiquito -> fin_last -> carta_last
    defaults: dict = {}
    defaults.update(fin_meta or {})
    defaults.update(fin_last or {})
    defaults.update(carta_last or {})

    # Siempre aseguramos llaves usadas por plantillas
    for k in [
        "CAUSAL_7_DETALLE_DIAS",
        "CAUSAL_7_FRASE_DIAS",
        "CAUSAL_8_FRASE",
        "CAUSAL_8_PRESET_KEY",
        "TIEMPO_SERVIDO",
        "FINIQUITO_AVISO_PREVIO",
        "FINIQUITO_ANIOS_SERVICIOS",
        "FINIQUITO_INDEM_VOLUNTARIA",
        "FINIQUITO_SUBTOTAL",
        "FINIQUITO_TOTAL_DESCTOS",
        "FINIQUITO_TOTAL_PAGO",
    ]:
        defaults.setdefault(k, "")

    # Asegurar TIEMPO_SERVIDO actualizado (mejor que el guardado)
    defaults["TIEMPO_SERVIDO"] = tiempo_servido_fmt or defaults.get("TIEMPO_SERVIDO", "")

    # ✅ Autofill desde Inasistencias (solo si aplica y si está vacío)
    try:
        defaults = _autofill_causal_7_from_inasistencias(desv, defaults)
    except Exception as e:
        _push_meta(desv, "carta_autofill_error", {"error": str(e)})
        db.session.commit()

    # ✅ Autofill Art.161: si causal==8, hay preset elegido y texto está vacío -> sugerir texto
    try:
        if int(getattr(desv, "causal_id", 0) or 0) == 8:
            preset_key = (defaults.get("CAUSAL_8_PRESET_KEY") or "").strip()
            if preset_key and not (defaults.get("CAUSAL_8_FRASE") or "").strip():
                defaults["CAUSAL_8_FRASE"] = _preset_text_by_key(preset_key)
    except Exception:
        pass

    # --- GET ---
    if request.method == "GET":
        return render_template(
            "desvinculaciones/carta_aviso_generar.html",
            desv=desv,
            formato=(request.args.get("formato") or "PDF").upper(),
            vals=defaults,

            contrato_fecha_inicio_fmt=contrato_fecha_inicio_fmt,
            tiempo_servido_fmt=tiempo_servido_fmt,
            tiempo_servido_hint=tiempo_servido_hint,

            # ✅ NUEVO: warning Art. 159 N°4
            warning_venc_plazo=warning_venc_plazo,

            # ✅ Presets para UI (lista de dicts)
            causal_8_presets=_CAUSAL_8_PRESETS,
        )

    # --- POST ---
    formato = (request.form.get("formato") or "PDF").upper()
    if formato not in ("DOCX", "PDF", "AMBOS"):
        formato = "PDF"

    # preset seleccionado en UI
    preset_key = (request.form.get("CAUSAL_8_PRESET_KEY") or "").strip().upper()

    overrides: dict[str, str] = {
        "CAUSAL_7_DETALLE_DIAS": (request.form.get("CAUSAL_7_DETALLE_DIAS") or "").strip(),
        "CAUSAL_7_FRASE_DIAS": (request.form.get("CAUSAL_7_FRASE_DIAS") or "").strip(),
        "CAUSAL_8_FRASE": (request.form.get("CAUSAL_8_FRASE") or "").strip(),
        "CAUSAL_8_PRESET_KEY": preset_key,
        "TIEMPO_SERVIDO": (tiempo_servido_fmt or "").strip(),
    }

    overrides["FINIQUITO_AVISO_PREVIO"] = _parse_money_to_str(request.form.get("FINIQUITO_AVISO_PREVIO", ""))
    overrides["FINIQUITO_ANIOS_SERVICIOS"] = _parse_money_to_str(request.form.get("FINIQUITO_ANIOS_SERVICIOS", ""))
    overrides["FINIQUITO_INDEM_VOLUNTARIA"] = _parse_money_to_str(request.form.get("FINIQUITO_INDEM_VOLUNTARIA", ""))

    _save_doc_inputs(desv, "CARTA_AVISO", overrides, "carta_config", extra_audit={"formato": formato})

    try:
        target_dir = _desv_target_dir(desv)
        ensure_dir(target_dir)

        docx_name = _carta_aviso_filename(desv, "docx")
        pdf_name = _carta_aviso_filename(desv, "pdf")

        docx_final = target_dir / docx_name
        pdf_final = target_dir / pdf_name

        out_tmp = Path(current_app.instance_path) / "generated_docs" / "desvinculaciones"
        ensure_dir(out_tmp)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        docx_tmp = out_tmp / f"tmp_carta_{desv.id}_{stamp}.docx"

        build_carta_aviso_docx(desv, docx_tmp, overrides=overrides)

        if formato in ("DOCX", "AMBOS"):
            docx_final.write_bytes(docx_tmp.read_bytes())

        if formato in ("PDF", "AMBOS"):
            pdf_tmp_dir = out_tmp / "pdf"
            ensure_dir(pdf_tmp_dir)
            pdf_tmp = convert_docx_to_pdf(docx_tmp, pdf_tmp_dir)
            pdf_final.write_bytes(pdf_tmp.read_bytes())

        if formato in ("DOCX", "AMBOS"):
            desv.carta_nombre = docx_name
            desv.carta_ruta = str(docx_final)
        else:
            desv.carta_nombre = pdf_name
            desv.carta_ruta = str(pdf_final)

        _push_meta(
            desv,
            "doc_carta_aviso",
            {
                "docx": str(docx_final) if formato in ("DOCX", "AMBOS") else "",
                "pdf": str(pdf_final) if formato in ("PDF", "AMBOS") else "",
                "estado": desv.estado,
                "formato": formato,
            },
        )

        db.session.commit()

        if formato == "DOCX":
            flash("Carta de aviso generada y guardada en Nextcloud: DOCX", "success")
        elif formato == "PDF":
            flash("Carta de aviso generada y guardada en Nextcloud: PDF", "success")
        else:
            flash("Carta de aviso generada y guardada en Nextcloud: DOCX + PDF", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"No se pudo generar la carta: {e}", "error")

    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# --- helpers nombres de archivo finiquito ---

_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def _clean_filename(s: str) -> str:
    s = (s or "").strip()
    s = _INVALID_FS_CHARS_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "SIN_NOMBRE"


def _finiquito_filename(desv: Desvinculacion, ext: str) -> str:
    t = desv.trabajador
    causal = getattr(desv.causal, "causal_resumida", "") or "Sin causal"
    fecha_iso = desv.fecha_termino.isoformat() if desv.fecha_termino else date.today().isoformat()

    nombre_trab = f"{t.ap_paterno or ''} {t.ap_materno or ''} {t.nombres or ''}".strip()
    base = f"{fecha_iso} Finiquito - {nombre_trab} ({causal})"

    return f"{_clean_filename(base)}.{ext.lower()}"


def _carta_aviso_filename(desv: Desvinculacion, ext: str) -> str:
    t = desv.trabajador
    causal = getattr(desv.causal, "causal_resumida", "") or "Sin causal"
    fecha_iso = desv.fecha_termino.isoformat() if desv.fecha_termino else date.today().isoformat()

    nombre_trab = f"{t.ap_paterno or ''} {t.ap_materno or ''} {t.nombres or ''}".strip()
    base = f"{fecha_iso} Carta de aviso - {nombre_trab} ({causal})"
    return f"{_clean_filename(base)}.{ext.lower()}"

@bp.post("/<int:desvinculacion_id>/calcular-finiquito")
@login_required
def calcular_finiquito_ajax(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado not in {"BORRADOR", "EMITIDA"}:
        return jsonify({"ok": False, "error": "Estado de desvinculación no válido para cálculo."}), 400

    tipo_remuneracion = (request.form.get("tipo_remuneracion") or "FIJA").strip().upper()
    if tipo_remuneracion not in {"FIJA", "VARIABLE", "MIXTA"}:
        tipo_remuneracion = "FIJA"

    aplicar_aviso_previo = (request.form.get("aplicar_aviso_previo") or "").strip() in {"1", "true", "on", "si", "SI"}
    aplicar_anios_servicio = (request.form.get("aplicar_anios_servicio") or "").strip() in {"1", "true", "on", "si", "SI"}

    incluir_colacion_base = (request.form.get("incluir_colacion_base") or "").strip() in {"1", "true", "on"}
    incluir_movilizacion_base = (request.form.get("incluir_movilizacion_base") or "").strip() in {"1", "true", "on"}

    # ✅ NUEVO: base indemnizatoria con gratificación
    incluir_gratificacion_base = (request.form.get("incluir_gratificacion_base") or "").strip() in {"1", "true", "on"}
    gratificacion_mensual = (request.form.get("gratificacion_mensual") or "").strip()

    var1 = (request.form.get("var_mes_1") or "").strip()
    var2 = (request.form.get("var_mes_2") or "").strip()
    var3 = (request.form.get("var_mes_3") or "").strip()

    movimientos = (
        VacacionMovimiento.query
        .filter(VacacionMovimiento.contrato_id == desv.contrato_id)
        .filter(VacacionMovimiento.fecha <= desv.fecha_termino)
        .order_by(VacacionMovimiento.fecha.asc(), VacacionMovimiento.id.asc())
        .all()
    )

    feriados_rows = (
        Feriado.query
        .filter(Feriado.activo.is_(True))
        .filter(Feriado.fecha >= desv.fecha_termino)
        .order_by(Feriado.fecha.asc())
        .all()
    )

    try:
        resumen = calcular_resumen_finiquito(
            desv=desv,
            movimientos=movimientos,
            feriados_rows=feriados_rows,
            tipo_remuneracion=tipo_remuneracion,
            var1=var1 or None,
            var2=var2 or None,
            var3=var3 or None,
            aplicar_aviso_previo=aplicar_aviso_previo,
            aplicar_anios_servicio=aplicar_anios_servicio,
            incluir_colacion_base=incluir_colacion_base,
            incluir_movilizacion_base=incluir_movilizacion_base,
            incluir_gratificacion_base=incluir_gratificacion_base,
            gratificacion_mensual=gratificacion_mensual or None,
            tope_meses_anios_servicio=11,
        )

        return jsonify({"ok": True, "resumen": resumen})

    except Exception as e:
        current_app.logger.exception("Error cálculo finiquito desv=%s", desv.id)
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/<int:desvinculacion_id>/generar-finiquito", methods=["GET", "POST"])
@login_required
def generar_finiquito(desvinculacion_id: int):
    """
    Flujo:
    - GET  -> muestra formulario (finiquito_generar.html) para elegir formato y cargar montos
    - POST -> genera DOCX/PDF/AMBOS y guarda en Nextcloud
    """
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    if desv.estado not in {"BORRADOR", "EMITIDA"}:
        flash("Solo puedes generar documentos en BORRADOR o EMITIDA.", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    extra = _compute_tiempo_servido(desv)

    # =========================
    # GET → mostrar formulario
    # =========================
    if request.method == "GET":
        vals = _get_doc_inputs(desv.id, "FINIQUITO") or {}

        for k in [
            "FINIQUITO_DIAS_FERIADO_A_PAGO",
            "FINIQUITO_FERIADO_PROPORCIONAL",
            "FINIQUITO_AVISO_PREVIO",
            "FINIQUITO_ANIOS_SERVICIOS",
            "FINIQUITO_INDEM_VOLUNTARIA",
            "FINIQUITO_OTROS",
            "FINIQUITO_MONTO_OTROS",
            "FINIQUITO_APORTE_EMP_SEG_CES",
            "FINIQUITO_DESCTO_1",
            "FINIQUITO_MONTO_DESCTO_1",
            "FINIQUITO_DESCTO_2",
            "FINIQUITO_MONTO_DESCTO_2",
            "FINIQUITO_SUBTOTAL",
            "FINIQUITO_TOTAL_DESCTOS",
            "FINIQUITO_TOTAL_PAGO",
            "TIEMPO_SERVIDO",
        ]:
            vals.setdefault(k, "")

        vals = {str(k): ("" if v is None else str(v)) for k, v in vals.items()}

        contrato_fecha_inicio_fmt = (
            extra["contrato_fecha_inicio"].strftime("%d-%m-%Y")
            if extra["contrato_fecha_inicio"]
            else ""
        )

        tiempo_servido_fmt = extra["tiempo_servido_txt"] or ""

        tiempo_servido_hint = (
            "Referencial para gestión. Para carta por “Necesidades de la empresa” "
            "se calculará con precisión calendario."
            if tiempo_servido_fmt
            else ""
        )

        meta = dict(desv.meta or {})
        calculo_finiquito_meta = meta.get("calculo_finiquito") if isinstance(meta.get("calculo_finiquito"), dict) else {}

        return render_template(
            "desvinculaciones/finiquito_generar.html",
            desv=desv,
            vals=vals,
            formato=(request.args.get("formato") or "PDF").upper(),
            next_url=(request.args.get("next") or "").strip(),
            contrato_fecha_inicio_fmt=contrato_fecha_inicio_fmt,
            tiempo_servido_fmt=tiempo_servido_fmt,
            tiempo_servido_hint=tiempo_servido_hint,
            calculo_finiquito_meta=calculo_finiquito_meta,
        )

    # =========================
    # POST → generar documentos
    # =========================
    formato = (request.form.get("formato") or "PDF").upper()
    if formato not in ("DOCX", "PDF", "AMBOS"):
        formato = "PDF"

    def _money_to_int(raw: str) -> int:
        s = (raw or "").strip()
        if not s:
            return 0
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0

    otros_nombre = (request.form.get("FINIQUITO_OTROS") or "").strip()
    dcto1_nombre = (request.form.get("FINIQUITO_DESCTO_1") or "").strip()
    dcto2_nombre = (request.form.get("FINIQUITO_DESCTO_2") or "").strip()

    feriado = _parse_money_to_str(request.form.get("FINIQUITO_FERIADO_PROPORCIONAL", ""))
    aviso = _parse_money_to_str(request.form.get("FINIQUITO_AVISO_PREVIO", ""))
    anios = _parse_money_to_str(request.form.get("FINIQUITO_ANIOS_SERVICIOS", ""))
    indem_vol = _parse_money_to_str(request.form.get("FINIQUITO_INDEM_VOLUNTARIA", ""))
    otros = _parse_money_to_str(request.form.get("FINIQUITO_MONTO_OTROS", ""))

    aporte_ces = _parse_money_to_str(request.form.get("FINIQUITO_APORTE_EMP_SEG_CES", ""))
    dcto1_m = _parse_money_to_str(request.form.get("FINIQUITO_MONTO_DESCTO_1", ""))
    dcto2_m = _parse_money_to_str(request.form.get("FINIQUITO_MONTO_DESCTO_2", ""))

    subtotal_i = (
        _money_to_int(feriado)
        + _money_to_int(aviso)
        + _money_to_int(anios)
        + _money_to_int(indem_vol)
        + _money_to_int(otros)
    )
    total_desc_i = (
        _money_to_int(aporte_ces)
        + _money_to_int(dcto1_m)
        + _money_to_int(dcto2_m)
    )
    total_pago_i = max(subtotal_i - total_desc_i, 0)

    subtotal = f"{subtotal_i:,}".replace(",", ".") if subtotal_i else "0"
    total_desc = f"{total_desc_i:,}".replace(",", ".") if total_desc_i else "0"
    total_pago = f"{total_pago_i:,}".replace(",", ".") if total_pago_i else "0"

    dias_feriado = (request.form.get("FINIQUITO_DIAS_FERIADO_A_PAGO") or "").strip()
    dias_feriado = dias_feriado.replace(".", ",")
    dias_feriado = re.sub(r"[^\d,]", "", dias_feriado)

    if dias_feriado.count(",") > 1:
        dias_feriado = dias_feriado.replace(",", "", dias_feriado.count(",") - 1)

    if not dias_feriado:
        dias_feriado = ""

    # ✅ Nuevo: detalle del asistente
    calculo_finiquito_payload = _parse_json_dict(request.form.get("CALCULO_FINIQUITO_JSON"))

    fin_inputs = {
        "FINIQUITO_DIAS_FERIADO_A_PAGO": dias_feriado,
        "FINIQUITO_FERIADO_PROPORCIONAL": feriado,
        "FINIQUITO_AVISO_PREVIO": aviso,
        "FINIQUITO_ANIOS_SERVICIOS": anios,
        "FINIQUITO_INDEM_VOLUNTARIA": indem_vol,
        "FINIQUITO_OTROS": otros_nombre,
        "FINIQUITO_MONTO_OTROS": otros,
        "FINIQUITO_APORTE_EMP_SEG_CES": aporte_ces,
        "FINIQUITO_DESCTO_1": dcto1_nombre,
        "FINIQUITO_MONTO_DESCTO_1": dcto1_m,
        "FINIQUITO_DESCTO_2": dcto2_nombre,
        "FINIQUITO_MONTO_DESCTO_2": dcto2_m,
        "FINIQUITO_SUBTOTAL": subtotal,
        "FINIQUITO_TOTAL_DESCTOS": total_desc,
        "FINIQUITO_TOTAL_PAGO": total_pago,
        "TIEMPO_SERVIDO": extra["tiempo_servido_txt"] or "",
    }

    next_url = (request.form.get("next_url") or request.args.get("next") or "").strip()

    try:
        target_dir = _desv_target_dir(desv)
        ensure_dir(target_dir)

        docx_name = _finiquito_filename(desv, "docx")
        pdf_name = _finiquito_filename(desv, "pdf")

        docx_final = target_dir / docx_name
        pdf_final = target_dir / pdf_name

        out_tmp = Path(current_app.instance_path) / "generated_docs" / "desvinculaciones"
        ensure_dir(out_tmp)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        docx_tmp = out_tmp / f"tmp_finiquito_{desv.id}_{stamp}.docx"

        # Persistencia en meta
        meta = dict(desv.meta or {})
        meta["finiquito_inputs"] = fin_inputs

        # ✅ Guardar detalle de cálculo solo si vino payload válido
        if calculo_finiquito_payload:
            meta["calculo_finiquito"] = calculo_finiquito_payload

        desv.meta = meta

        _push_meta(desv, "finiquito_config", {"formato": formato, "inputs": fin_inputs})

        if calculo_finiquito_payload:
            _push_meta(
                desv,
                "calculo_finiquito_guardado",
                {
                    "fuente": "asistente_modal",
                    "keys": list(calculo_finiquito_payload.keys()),
                },
            )

        # Persistencia en tabla inputs (sin commit todavía)
        _upsert_doc_inputs(desv, "FINIQUITO", fin_inputs)

        try:
            build_finiquito_docx(desv, docx_tmp, overrides=fin_inputs)  # type: ignore[arg-type]
        except TypeError:
            build_finiquito_docx(desv, docx_tmp)

        if formato in ("DOCX", "AMBOS"):
            docx_final.write_bytes(docx_tmp.read_bytes())

        if formato in ("PDF", "AMBOS"):
            pdf_tmp_dir = out_tmp / "pdf"
            ensure_dir(pdf_tmp_dir)
            pdf_tmp = convert_docx_to_pdf(docx_tmp, pdf_tmp_dir)
            pdf_final.write_bytes(pdf_tmp.read_bytes())

        if formato in ("DOCX", "AMBOS"):
            desv.finiquito_nombre = docx_name
            desv.finiquito_ruta = str(docx_final)
        else:
            desv.finiquito_nombre = pdf_name
            desv.finiquito_ruta = str(pdf_final)

        _push_meta(
            desv,
            "doc_finiquito",
            {
                "docx": str(docx_final) if formato in ("DOCX", "AMBOS") else "",
                "pdf": str(pdf_final) if formato in ("PDF", "AMBOS") else "",
                "estado": desv.estado,
                "formato": formato,
            },
        )

        _commit_or_rollback(f"generar_finiquito archivos desv={desv.id}")

        if formato == "DOCX":
            flash("Finiquito generado y guardado en Nextcloud: DOCX", "success")
        elif formato == "PDF":
            flash("Finiquito generado y guardado en Nextcloud: PDF", "success")
        else:
            flash("Finiquito generado y guardado en Nextcloud: DOCX + PDF", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"No se pudo generar el finiquito: {e}", "error")
        current_app.logger.exception("Error generando finiquito desv=%s", desv.id)

    if next_url:
        return redirect(next_url)
    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))


# ---------------------------
# Anular
# ---------------------------

@bp.post("/<int:desvinculacion_id>/anular")
@login_required
def anular(desvinculacion_id: int):
    """
    Anula una desvinculación.
    - Permite anular BORRADOR y EMITIDA.
    - NO revertimos contrato/trabajador automáticamente.
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


def _parse_fecha_pago_any(raw: str | None) -> str:
    """
    Devuelve ISO 'YYYY-MM-DD' o ''.
    Acepta:
      - YYYY-MM-DD
      - DD-MM-YYYY
      - DD/MM/YYYY
    """
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.replace("/", "-")

    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass

    return ""


@bp.post("/<int:desvinculacion_id>/pago-finiquito")
@login_required
def pago_finiquito_post(desvinculacion_id: int):
    desv = Desvinculacion.query.get_or_404(desvinculacion_id)

    estado_pago = (request.form.get("estado_pago") or "").strip().upper()
    if estado_pago not in {"PAGADO", "PENDIENTE", ""}:
        estado_pago = ""

    fecha_pago_raw = (request.form.get("fecha_pago") or "").strip()
    fecha_pago = _parse_fecha_pago_any(fecha_pago_raw)

    # Si el estado es PAGADO, exigimos fecha válida
    if estado_pago == "PAGADO" and not fecha_pago:
        flash("Si el estado es PAGADO, debes indicar una fecha válida (YYYY-MM-DD o DD-MM-YYYY).", "warning")
        return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))

    medio = (request.form.get("medio_pago") or "").strip()[:50]
    obs = (request.form.get("obs_pago") or "").strip()

    # ✅ meta seguro: copiar dict para asegurar “dirty”
    meta = dict(desv.meta or {})
    meta["pago_finiquito"] = {
        "estado": estado_pago,
        "fecha_pago": fecha_pago,  # ISO estable
        "medio": medio,
        "obs": obs,
    }
    desv.meta = meta
    flag_modified(desv, "meta")  # ✅ blindaje total

    _push_meta(
        desv,
        "audit_pago_finiquito",
        {
            "estado": estado_pago,
            "fecha_pago": fecha_pago,
            "medio": medio,
            "obs": obs[:2000],
        },
    )

    db.session.commit()
    flash("Control de pago de finiquito actualizado.", "success")

    next_url = (request.form.get("next") or "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("desvinculaciones.detalle", desvinculacion_id=desv.id))