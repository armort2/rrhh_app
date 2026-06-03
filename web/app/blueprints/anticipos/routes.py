# web/app/blueprints/anticipos/routes.py
from __future__ import annotations

import os
import uuid
import json
import glob
from io import BytesIO
from datetime import datetime, date
from typing import Optional, Tuple

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    make_response,
    current_app,
    send_file,
    session,
    abort,
)
from flask_login import login_required, current_user
from sqlalchemy import func, and_, or_, literal, case
from sqlalchemy.orm import aliased
from jinja2 import TemplateError

from ...extensions import db
from ...models import (
    AnticipoNomina,
    AnticipoDetalle,
    Obra,
    Trabajador,
    Cargo,
    Contrato,
    Banco,
    Empleador,
    SolicitudFondos,
    SolicitudFondosItem,
)

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


def _rut_sin_puntos_con_guion(rut_raw: str | None) -> str | None:
    """
    Normaliza a: 12345678-9 (sin puntos, con guión).
    Acepta: 12.345.678-9 / 12345678-9 / 12345678 (si no hay DV, devuelve base sin inventar DV).
    """
    if not rut_raw:
        return None

    s = str(rut_raw).strip().replace(" ", "")
    if not s:
        return None

    s = s.replace(".", "")
    if "-" in s:
        base, dv = s.split("-", 1)
        base_digits = "".join(ch for ch in base if ch.isdigit())
        dv = dv.strip().upper()
        if base_digits and dv:
            return f"{base_digits}-{dv}"
        return s

    base_digits = "".join(ch for ch in s if ch.isdigit())
    return base_digits or s


def _rut_trabajador_para_edig(t: Trabajador | None, det: AnticipoDetalle | None) -> str | None:
    # Preferir rut/dv del Trabajador si existen
    if t is not None:
        rut = getattr(t, "rut", None)
        dv = getattr(t, "dv", None)
        if rut:
            base = "".join(ch for ch in str(rut).strip().replace(".", "") if ch.isdigit())
            if dv:
                return f"{base}-{str(dv).strip().upper()}"
            # fallback sin DV (no inventamos)
            return base or None

    # fallback a lo que haya en detalle
    if det is not None:
        return _rut_sin_puntos_con_guion(getattr(det, "rut", None))

    return None


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in s)
    s = s.replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s or "archivo"



def _build_nros_contrato_edig(contrato_ids: list[int], periodo_inicio: date | None = None, periodo_fin: date | None = None) -> dict[int, int]:
    """
    Devuelve el Nro. Contrato que debe viajar al CSV EDIG para cada contrato_id.

    Regla funcional:
    - El anticipo pertenece a una línea de contrato, no solo al trabajador.
    - Para EDIG usamos un ordinal estable por trabajador + empleador, ordenado por
      fecha de inicio e id de contrato: 1, 2, 3...
    - Esto evita que dos anticipos de un mismo RUT queden ambos como contrato 1.
    """
    ids = sorted({int(x) for x in (contrato_ids or []) if x})
    if not ids:
        return {}

    base_rows = (
        db.session.query(Contrato.id, Contrato.trabajador_id, Contrato.empleador_id)
        .filter(Contrato.id.in_(ids))
        .all()
    )

    pares = {
        (int(trabajador_id), int(empleador_id))
        for _cid, trabajador_id, empleador_id in base_rows
        if trabajador_id and empleador_id
    }
    if not pares:
        return {cid: 1 for cid in ids}

    q = (
        db.session.query(Contrato)
        .filter(Contrato.trabajador_id.in_({p[0] for p in pares}))
        .filter(Contrato.empleador_id.in_({p[1] for p in pares}))
    )

    # Si se entrega período, numeramos contratos que intersectan ese mes.
    # Así el ordinal representa el set contractual activo/importable del período.
    if periodo_inicio is not None and periodo_fin is not None:
        q = q.filter(Contrato.fecha_inicio.isnot(None))
        q = q.filter(Contrato.fecha_inicio < periodo_fin)
        q = q.filter(func.coalesce(Contrato.fecha_termino, date(2999, 12, 31)) >= periodo_inicio)

    contratos = q.order_by(Contrato.trabajador_id.asc(), Contrato.empleador_id.asc(), Contrato.fecha_inicio.asc(), Contrato.id.asc()).all()

    grupos: dict[tuple[int, int], list[Contrato]] = {}
    for c in contratos:
        if not c.trabajador_id or not c.empleador_id:
            continue
        key = (int(c.trabajador_id), int(c.empleador_id))
        if key in pares:
            grupos.setdefault(key, []).append(c)

    out: dict[int, int] = {}
    for key, items in grupos.items():
        for idx, c in enumerate(items, start=1):
            out[int(c.id)] = idx

    # Fallback conservador: si algún contrato no entró por datos incompletos, no rompemos exportación.
    for cid in ids:
        out.setdefault(cid, 1)
    return out




def _is_hex_token(s: str) -> bool:
    s = (s or "").strip().lower()
    # token uuid4 hex = 32 chars
    return len(s) == 32 and all(c in "0123456789abcdef" for c in s)


def _tmp_edig_dir() -> str:
    d = os.path.join(current_app.instance_path, "tmp_edig")
    os.makedirs(d, exist_ok=True)
    return d


def _meta_path(token: str) -> str:
    return os.path.join(_tmp_edig_dir(), f"{token}_meta.json")


def _find_csv_by_token(token: str) -> tuple[str, str] | None:
    if not _is_hex_token(token):
        return None
    tmp_dir = _tmp_edig_dir()
    matches = glob.glob(os.path.join(tmp_dir, f"{token}_*.csv"))
    if not matches:
        return None
    path = sorted(matches)[-1]
    filename = os.path.basename(path).split("_", 1)[-1]
    return path, filename


def _find_excluidos_by_token(token: str) -> str | None:
    if not _is_hex_token(token):
        return None
    path = os.path.join(_tmp_edig_dir(), f"{token}_excluidos.json")
    return path if os.path.exists(path) else None


def _load_edig_meta(token: str) -> dict | None:
    if not _is_hex_token(token):
        return None
    mp = _meta_path(token)
    if not os.path.exists(mp):
        return None
    try:
        with open(mp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None





def _ensure_nomina_origen(n: AnticipoNomina, default: str = "MANUAL") -> None:
    # Si aún no existe la columna en BD, no revienta.
    if hasattr(n, "origen"):
        if not getattr(n, "origen", None):
            setattr(n, "origen", default)


def _allowed_centros_for_user() -> set[str]:
    """
    Centros de costo permitidos para el usuario, según sus obras asignadas.
    ADMIN: sin restricción (set vacío como 'no filtrar').
    """
    if current_user.has_role("ADMIN"):
        return set()

    obra_ids = [o.id for o in (current_user.obras or [])]
    if not obra_ids:
        return set()

    rows = (
        db.session.query(func.coalesce(Obra.centro_costo, ""))
        .filter(Obra.id.in_(obra_ids))
        .distinct()
        .all()
    )
    return {str(r[0]).strip().upper() for r in rows if r and str(r[0]).strip()}


def _require_nomina_access(nomina: AnticipoNomina) -> None:
    """
    Control de acceso por nómina (scope = centro_costo):
    - ADMIN: OK
    - OPERADOR/REVISOR: solo si el centro de costo de la nómina está dentro de sus centros permitidos
    """
    if current_user.has_role("ADMIN"):
        return

    allowed = _allowed_centros_for_user()
    cc = (nomina.centro_costo or "").strip().upper()

    if not allowed or cc not in allowed:
        abort(403)


def _sync_detalles_desde_cc(nomina: AnticipoNomina) -> dict:
    """
    Sincroniza AnticipoDetalle a nivel CONTRATO, no solo trabajador.

    Esto corrige el caso de trabajadores con 2 contratos en el mismo período:
    cada contrato vigente/intersectado en el CC genera su propia línea de anticipo.
    """
    cc = _upper(nomina.centro_costo)

    periodo_inicio = date(int(nomina.anio), int(nomina.mes), 1)
    periodo_fin = (
        date(int(nomina.anio) + 1, 1, 1)
        if int(nomina.mes) == 12
        else date(int(nomina.anio), int(nomina.mes) + 1, 1)
    )

    contratos_cc = (
        db.session.query(Trabajador, Contrato, Obra)
        .join(Contrato, Contrato.trabajador_id == Trabajador.id)
        .join(Obra, Obra.id == Contrato.obra_id)
        .filter(func.upper(func.coalesce(Obra.centro_costo, "")) == cc)
        .filter(Contrato.fecha_inicio.isnot(None))
        .filter(Contrato.fecha_inicio < periodo_fin)
        .filter(func.coalesce(Contrato.fecha_termino, date(2999, 12, 31)) >= periodo_inicio)
        .order_by(
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            Contrato.id.asc(),
        )
        .all()
    )

    elegibles_por_contrato = {int(c.id): (t, c, obra) for t, c, obra in contratos_cc if c and c.id}
    contratos_por_trabajador: dict[int, list[tuple[Trabajador, Contrato, Obra]]] = {}
    for t, c, obra in contratos_cc:
        contratos_por_trabajador.setdefault(int(t.id), []).append((t, c, obra))

    detalles_existentes = (
        AnticipoDetalle.query
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .order_by(AnticipoDetalle.id.asc())
        .all()
    )

    insertados = 0
    eliminados = 0
    conservados_con_monto = 0
    actualizados_contrato = 0

    # Backfill suave: detalles antiguos sin contrato_id pasan a una línea por contrato.
    # Si el trabajador tiene más de un contrato, se asigna el detalle existente al contrato más reciente
    # y luego se insertan las líneas faltantes con monto 0.
    for d in detalles_existentes:
        if getattr(d, "contrato_id", None):
            continue
        if not d.trabajador_id:
            continue

        opciones = contratos_por_trabajador.get(int(d.trabajador_id), [])
        if not opciones:
            continue

        # contrato más reciente para conservar la línea/monto existente
        t, c, obra = sorted(opciones, key=lambda row: int(row[1].id or 0), reverse=True)[0]
        d.contrato_id = c.id
        d.obra_id = c.obra_id or (obra.id if obra else d.obra_id)
        d.nombre_obra = (obra.nombre if obra else d.nombre_obra)
        d.centro_costo = cc
        if len(opciones) > 1:
            msg = f"Backfill automático: trabajador con {len(opciones)} contratos en el período; revisar distribución por contrato."
            d.observacion = (str(d.observacion).strip() + " | " if d.observacion else "") + msg
            if d.estado_linea == "OK":
                d.estado_linea = "AMBIGUO_CONTRATO"
        actualizados_contrato += 1

    existentes_contrato_ids = {
        int(d.contrato_id)
        for d in detalles_existentes
        if getattr(d, "contrato_id", None) is not None
    }

    # Insertar una línea por contrato faltante
    for contrato_id, (t, c, obra) in elegibles_por_contrato.items():
        if contrato_id in existentes_contrato_ids:
            continue

        d = AnticipoDetalle(
            nomina_id=nomina.id,
            trabajador_id=t.id,
            contrato_id=c.id,
            obra_id=c.obra_id or (obra.id if obra else None),
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

    # Eliminar obsoletos sin monto: ahora la llave válida es contrato_id.
    for d in detalles_existentes:
        contrato_id = int(d.contrato_id) if getattr(d, "contrato_id", None) else None
        tid = int(d.trabajador_id) if d.trabajador_id else None

        vigente = contrato_id in elegibles_por_contrato if contrato_id else (tid in contratos_por_trabajador if tid else False)
        if vigente:
            continue

        monto_actual = float(d.monto or 0)
        if monto_actual != 0:
            conservados_con_monto += 1
            current_app.logger.warning(
                "Anticipos sync: detalle obsoleto conservado por tener monto. "
                "nomina_id=%s detalle_id=%s trabajador_id=%s contrato_id=%s monto=%s",
                nomina.id, d.id, tid, contrato_id, monto_actual
            )
            continue

        db.session.delete(d)
        eliminados += 1

    db.session.commit()

    return {
        "nomina_id": nomina.id,
        "insertados": insertados,
        "eliminados": eliminados,
        "conservados_con_monto": conservados_con_monto,
        "actualizados_contrato": actualizados_contrato,
        "total_elegibles": len(elegibles_por_contrato),
    }

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
@role_required("ADMIN", "OPERADOR", "REVISOR")
def listado():
    q_cc = _upper(request.args.get("centro_costo"))
    q_periodo = (request.args.get("periodo") or "").strip()  # "YYYY-MM"
    q_estado = _upper(request.args.get("estado"))

    q = AnticipoNomina.query

    # ✅ Seguridad: si no es ADMIN, limitar por centros de costo permitidos
    allowed_cc = set()
    if not current_user.has_role("ADMIN"):
        allowed_cc = _allowed_centros_for_user()
        if not allowed_cc:
            flash("No tienes obras asignadas. Solicita acceso a una obra para ver nóminas.", "warning")
            return render_template(
                "anticipos/anticipos_listado.html",
                nominas=[],
                centros=[],
                q_cc=q_cc,
                q_periodo=q_periodo,
                q_estado=q_estado,
            )
        q = q.filter(AnticipoNomina.centro_costo.in_(sorted(allowed_cc)))

    if q_cc:
        # Si el usuario fuerza un CC por querystring, igual quedará contenido por el filtro anterior
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

    # Centros para dropdown (no mostrar CC ajenos)
    centros_q = db.session.query(Obra.centro_costo).filter(Obra.centro_costo.isnot(None))
    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in (current_user.obras or [])]
        if obra_ids:
            centros_q = centros_q.filter(Obra.id.in_(obra_ids))
        else:
            centros_q = centros_q.filter(literal(False))

    centros = [r[0] for r in centros_q.distinct().order_by(Obra.centro_costo.asc()).all()]

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
    # Centros visibles (OPERADOR: solo sus CC)
    centros_q = db.session.query(Obra.centro_costo).filter(Obra.centro_costo.isnot(None))
    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in (current_user.obras or [])]
        if obra_ids:
            centros_q = centros_q.filter(Obra.id.in_(obra_ids))
        else:
            centros_q = centros_q.filter(literal(False))

    centros = [r[0] for r in centros_q.distinct().order_by(Obra.centro_costo.asc()).all()]

    if request.method == "POST":
        cc = _upper(request.form.get("centro_costo"))
        anio = _to_int(request.form.get("anio"))
        mes = _to_int(request.form.get("mes"))

        if not cc or not anio or not mes:
            flash("Completa centro de costo, año y mes.", "error")
            return redirect(url_for("anticipos.nueva"))

        # ✅ Seguridad: OPERADOR solo puede crear/abrir en sus CC
        if not current_user.has_role("ADMIN"):
            allowed_cc = _allowed_centros_for_user()
            if not allowed_cc or cc not in allowed_cc:
                abort(403)

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
            # Validar acceso si existe
            _require_nomina_access(nomina)
            flash(f"Nómina existente #{nomina.id}. Se abrirá para edición.", "info")

        # Sincronizar trabajadores del CC
        res_sync = _sync_detalles_desde_cc(nomina)

        if res_sync.get("actualizados_contrato", 0) > 0:
            flash(f"Se actualizaron {res_sync['actualizados_contrato']} líneas antiguas para asociarlas a contrato.", "info")

        if res_sync.get("insertados", 0) > 0:
            flash(f"Se agregaron {res_sync['insertados']} líneas de contrato a la nómina.", "success")

        if res_sync.get("eliminados", 0) > 0:
            flash(f"Se eliminaron {res_sync['eliminados']} trabajadores que ya no estaban vigentes en el período.", "info")

        if res_sync.get("conservados_con_monto", 0) > 0:
            flash(
                f"Se detectaron {res_sync['conservados_con_monto']} líneas obsoletas con monto distinto de 0; "
                f"no se eliminaron automáticamente.",
                "warning",
            )

        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

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

        # ✅ Seguridad: OPERADOR solo puede importar en sus CC
        if not current_user.has_role("ADMIN"):
            allowed_cc = _allowed_centros_for_user()
            if not allowed_cc or cc not in allowed_cc:
                abort(403)

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
            _require_nomina_access(nomina)
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

    centros_q = db.session.query(Obra.centro_costo).filter(Obra.centro_costo.isnot(None))
    if not current_user.has_role("ADMIN"):
        obra_ids = [o.id for o in (current_user.obras or [])]
        if obra_ids:
            centros_q = centros_q.filter(Obra.id.in_(obra_ids))
        else:
            centros_q = centros_q.filter(literal(False))
    centros = [r[0] for r in centros_q.distinct().order_by(Obra.centro_costo.asc()).all()]

    return render_template("anticipos/anticipos_importar.html", centros=centros)


# ---------------------------
# Detalle nómina (planilla editable + mes anterior referencia)
# ---------------------------
@bp.route("/<int:nomina_id>", methods=["GET"])
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def detalle(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    # Opción: volver a sincronizar (por si faltan trabajadores nuevos)
    # ✅ Solo ADMIN/OPERADOR pueden sincronizar
    if (request.args.get("sync") or "") == "1":
        if not (current_user.has_role("ADMIN") or current_user.has_role("OPERADOR")):
            abort(403)
        if nomina.estado == "BORRADOR":
            res_sync = _sync_detalles_desde_cc(nomina)

            if res_sync.get("actualizados_contrato", 0) > 0:
                flash(f"Sync CC: se actualizaron {res_sync['actualizados_contrato']} líneas antiguas para asociarlas a contrato.", "info")

            if res_sync.get("insertados", 0) > 0:
                flash(f"Sync CC: se agregaron {res_sync['insertados']} líneas de contrato.", "success")

            if res_sync.get("eliminados", 0) > 0:
                flash(f"Sync CC: se eliminaron {res_sync['eliminados']} trabajadores no vigentes para el período.", "info")

            if res_sync.get("conservados_con_monto", 0) > 0:
                flash(
                    f"Sync CC: {res_sync['conservados_con_monto']} líneas obsoletas se conservaron por tener monto distinto de 0.",
                    "warning",
                )
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    q_text = (request.args.get("q") or "").strip()
    q_obra_id = _to_int(request.args.get("obra_id"))  # (opcional)
    q_tipo = (request.args.get("tipo_trabajador") or "").strip()

    # ✅ Nuevo: múltiples cargos
    q_cargo_ids = []
    for raw in request.args.getlist("cargo_ids"):
        cid = _to_int(raw)
        if cid:
            q_cargo_ids.append(cid)

    # Quitar duplicados preservando orden
    q_cargo_ids = list(dict.fromkeys(q_cargo_ids))

    # Nómina mes anterior (misma CC)
    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    if nomina_prev:
        _require_nomina_access(nomina_prev)
    nomina_prev_id = nomina_prev.id if nomina_prev else None

    PrevDet = aliased(AnticipoDetalle)
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)

    # Contrato vigente EN EL PERÍODO DE LA NÓMINA y en el mismo CC
    periodo_inicio = date(int(nomina.anio), int(nomina.mes), 1)
    periodo_fin = (
        date(int(nomina.anio) + 1, 1, 1)
        if int(nomina.mes) == 12
        else date(int(nomina.anio), int(nomina.mes) + 1, 1)
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
            func.coalesce(ContratoV.sueldo_base, 0).label("sueldo_base"),
            ContratoV.fecha_inicio.label("fecha_ingreso"),
            ContratoV.id.label("contrato_id"),
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(ContratoV, ContratoV.id == AnticipoDetalle.contrato_id)
        # Cargo efectivo: primero el cargo del contrato del detalle; si es línea antigua sin contrato, cae al cargo maestro del trabajador.
        .outerjoin(Cargo, Cargo.id == func.coalesce(ContratoV.cargo_id, Trabajador.cargo_id))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
                # Ideal: mismo contrato. Compatibilidad: nóminas antiguas sin contrato_id.
                (
                    (PrevDet.contrato_id == AnticipoDetalle.contrato_id)
                    | (PrevDet.contrato_id.is_(None))
                    | (AnticipoDetalle.contrato_id.is_(None))
                ),
            ),
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

    # ✅ Nuevo: múltiples cargos
    if q_cargo_ids:
        q = q.filter(Cargo.id.in_(q_cargo_ids))

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
    total_filtrado = 0.0

    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev, sueldo_base, fecha_ingreso, contrato_id in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        monto_actual = float(d.monto or 0)
        total_filtrado += monto_actual

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "sueldo_base": float(sueldo_base or 0),
                "fecha_ingreso": fecha_ingreso,
                "contrato_id": contrato_id or getattr(d, "contrato_id", None),
            }
        )

    # Total general de la nómina completa (sin filtros)
    total_monto = (
        db.session.query(func.coalesce(func.sum(AnticipoDetalle.monto), 0))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    # ==========================
    # KPIs Integración SF (REMU)
    # ==========================
    total_integrado = (
        db.session.query(func.coalesce(func.sum(SolicitudFondosItem.monto), 0))
        .filter(SolicitudFondosItem.seccion == "REMU")
        .filter(SolicitudFondosItem.anticipo_nomina_id == nomina.id)
        .scalar()
    ) or 0

    pendiente_integrar = float(total_monto or 0) - float(total_integrado or 0)
    if pendiente_integrar < 0:
        pendiente_integrar = 0  # por seguridad contable

    # (Opcional PRO) desglose por SF
    integracion_por_sf = (
        db.session.query(
            SolicitudFondos.id.label("sf_id"),
            SolicitudFondos.numero.label("sf_numero"),
            SolicitudFondos.estado.label("sf_estado"),
            SolicitudFondos.fecha_solicitud.label("sf_fecha"),
            func.coalesce(func.sum(SolicitudFondosItem.monto), 0).label("sf_total"),
            func.count(SolicitudFondosItem.id).label("sf_count"),
        )
        .join(SolicitudFondos, SolicitudFondos.id == SolicitudFondosItem.solicitud_id)
        .filter(SolicitudFondosItem.seccion == "REMU")
        .filter(SolicitudFondosItem.anticipo_nomina_id == nomina.id)
        .group_by(
            SolicitudFondos.id,
            SolicitudFondos.numero,
            SolicitudFondos.estado,
            SolicitudFondos.fecha_solicitud,
        )
        .order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc())
        .all()
    )

    obras = (
        db.session.query(Obra.id, Obra.nombre)
        .join(AnticipoDetalle, AnticipoDetalle.obra_id == Obra.id)
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .distinct()
        .order_by(Obra.nombre.asc())
        .all()
    )

    tipos_trabajador = [
        r[0]
        for r in (
            db.session.query(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO"))
            .select_from(AnticipoDetalle)
            .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
            .filter(AnticipoDetalle.nomina_id == nomina.id)
            .distinct()
            .order_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").asc())
            .all()
        )
    ]
    tipos_trabajador = [t for t in tipos_trabajador if t]

    cargos = (
        db.session.query(Cargo.id, Cargo.nombre)
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(ContratoV, ContratoV.id == AnticipoDetalle.contrato_id)
        .outerjoin(Cargo, Cargo.id == func.coalesce(ContratoV.cargo_id, Trabajador.cargo_id))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .filter(Cargo.id.isnot(None))
        .distinct()
        .order_by(Cargo.nombre.asc())
        .all()
    )

    # ✅ Subtotales usando el mismo filtro aplicado
    q_subtotales = (
        db.session.query(
            func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").label("tipo"),
            func.coalesce(func.sum(AnticipoDetalle.monto), 0).label("total"),
            func.count(AnticipoDetalle.id).label("cantidad"),
        )
        .select_from(AnticipoDetalle)
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(ContratoV, ContratoV.id == AnticipoDetalle.contrato_id)
        .outerjoin(Cargo, Cargo.id == func.coalesce(ContratoV.cargo_id, Trabajador.cargo_id))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if q_obra_id:
        q_subtotales = q_subtotales.filter(AnticipoDetalle.obra_id == q_obra_id)

    if q_text:
        like = f"%{q_text}%"
        q_subtotales = q_subtotales.filter(
            (func.coalesce(AnticipoDetalle.rut, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.nombre_completo, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.nombre_obra, "").ilike(like))
            | (func.coalesce(Cargo.nombre, "").ilike(like))
            | (func.coalesce(Trabajador.tipo_trabajador, "").ilike(like))
            | (func.coalesce(AnticipoDetalle.observacion, "").ilike(like))
        )

    if q_tipo:
        q_subtotales = q_subtotales.filter(func.coalesce(Trabajador.tipo_trabajador, "").ilike(q_tipo))

    if q_cargo_ids:
        q_subtotales = q_subtotales.filter(Cargo.id.in_(q_cargo_ids))

    subtotales_tipo = (
        q_subtotales
        .group_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO"))
        .order_by(func.coalesce(Trabajador.tipo_trabajador, "SIN TIPO").asc())
        .all()
    )

    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    # ✅ Ahora: permitir ver SF candidatas aunque nómina esté BORRADOR/ENVIADA/VISADA
    solicitudes_quincena = []
    if current_user.has_role("ADMIN") or current_user.has_role("OPERADOR"):
        solicitudes_quincena = (
            SolicitudFondos.query
            .filter(SolicitudFondos.centro_costo == (nomina.centro_costo or "").strip().upper())
            .filter(SolicitudFondos.periodo_tipo == "QUINCENA")
            .filter(SolicitudFondos.estado.in_(["BORRADOR", "ENVIADA", "APROBADA"]))
            .order_by(SolicitudFondos.fecha_solicitud.desc(), SolicitudFondos.id.desc())
            .limit(30)
            .all()
        )

    return render_template(
        "anticipos/anticipos_detalle.html",
        nomina=nomina,
        detalles=detalles,
        total_monto=total_monto,
        total_filtrado=total_filtrado,
        obras=obras,
        tipos_trabajador=tipos_trabajador,
        cargos=cargos,
        subtotales_tipo=subtotales_tipo,
        q_text=q_text,
        q_obra_id=q_obra_id,
        q_tipo=q_tipo,
        q_cargo_ids=q_cargo_ids,
        nomina_prev=nomina_prev,
        periodo_prev_str=periodo_prev_str,
        solicitudes_quincena=solicitudes_quincena,
        total_integrado=total_integrado,
        pendiente_integrar=pendiente_integrar,
        integracion_por_sf=integracion_por_sf,
    )


# ---------------------------
# Guardar planilla (monto + observación)
# ---------------------------
@bp.post("/<int:nomina_id>/guardar")
@login_required
@role_required("ADMIN", "OPERADOR")
def guardar(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    if nomina.estado != "BORRADOR":
        flash("Solo se puede editar una nómina en estado BORRADOR.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    detalles_db = AnticipoDetalle.query.filter_by(nomina_id=nomina.id).all()

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
    _require_nomina_access(nomina)

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

    _require_nomina_access(nomina_prev)

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
    _require_nomina_access(nomina)

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
    _require_nomina_access(nomina)

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
    _require_nomina_access(nomina)

    if nomina.estado == "BORRADOR":
        flash("La nómina ya está en BORRADOR.", "info")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    nomina.estado = "BORRADOR"
    db.session.commit()
    flash("Nómina revertida a BORRADOR. Edición habilitada.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


@bp.post("/<int:nomina_id>/integrar_sf")
@login_required
@role_required("ADMIN", "OPERADOR")
def integrar_sf(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    # ✅ Permitimos integrar desde BORRADOR / ENVIADA_A_VISACION / VISADA
    estado_nom = (nomina.estado or "").strip().upper()
    if estado_nom not in {"BORRADOR", "ENVIADA_A_VISACION", "VISADA"}:
        flash("Estado de nómina no permite integración a Solicitud de Fondos.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    solicitud_id = _to_int(request.form.get("solicitud_id"))
    if not solicitud_id:
        flash("Debes seleccionar una Solicitud de Fondos.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    solicitud = SolicitudFondos.query.get_or_404(solicitud_id)

    # Validaciones “corporativas”
    cc_nom = (nomina.centro_costo or "").strip().upper()
    cc_sf = (solicitud.centro_costo or "").strip().upper()

    if cc_sf != cc_nom:
        flash("La Solicitud de Fondos no corresponde al mismo Centro de Costo de la nómina.", "danger")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    if (solicitud.periodo_tipo or "").strip().upper() != "QUINCENA":
        flash("La Solicitud de Fondos seleccionada no es de tipo QUINCENA.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    # 🔒 Mantenemos regla: SOLO BORRADOR para integrar (control de flujo)
    if (solicitud.estado or "").strip().upper() != "BORRADOR":
        flash("La Solicitud de Fondos debe estar en estado BORRADOR para integrar anticipos.", "warning")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    # Validación de período (evitar mezclar meses)
    ref = getattr(solicitud, "periodo_desde", None) or getattr(solicitud, "fecha_solicitud", None)
    if ref:
        try:
            if int(ref.year) != int(nomina.anio) or int(ref.month) != int(nomina.mes):
                flash(
                    f"Período inconsistente: la SF referencia {int(ref.year):04d}-{int(ref.month):02d} "
                    f"y la nómina es {int(nomina.anio):04d}-{int(nomina.mes):02d}.",
                    "warning",
                )
                return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))
        except Exception:
            pass

    # Rango mensual (intersección de contratos)
    periodo_inicio = date(int(nomina.anio), int(nomina.mes), 1)
    periodo_fin = date(int(nomina.anio) + 1, 1, 1) if int(nomina.mes) == 12 else date(int(nomina.anio), int(nomina.mes) + 1, 1)

    # Líneas con monto > 0
    detalles = (
        AnticipoDetalle.query
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .filter(func.coalesce(AnticipoDetalle.monto, 0) > 0)
        .order_by(AnticipoDetalle.id.asc())
        .all()
    )
    if not detalles:
        flash("No hay líneas con monto mayor a 0 para integrar.", "info")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    wipe = (request.form.get("wipe_anticipo") or "") == "1"

    insertados = 0
    omitidos = 0
    deleted = 0

    try:
        # 🧹 Wipe quirúrgico: SOLO anticipos de ESTA nómina en ESTA SF (REMU)
        if wipe:
            deleted = (
                SolicitudFondosItem.query
                .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
                .filter(SolicitudFondosItem.seccion == "REMU")
                .filter(SolicitudFondosItem.anticipo_nomina_id == nomina.id)
                .delete(synchronize_session=False)
            ) or 0
            db.session.flush()

        # Orden: continuar desde el máximo existente
        max_orden = (
            db.session.query(func.coalesce(func.max(SolicitudFondosItem.orden), 0))
            .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
            .scalar()
        ) or 0

        for det in detalles:
            # Evitar duplicado por anticipo_detalle_id dentro de esta SF
            ya = (
                SolicitudFondosItem.query
                .filter(SolicitudFondosItem.solicitud_id == solicitud.id)
                .filter(SolicitudFondosItem.anticipo_detalle_id == det.id)
                .first()
            )
            if ya:
                omitidos += 1
                continue

            trabajador_id = det.trabajador_id
            contrato_id = getattr(det, "contrato_id", None)

            # Fallback para nóminas antiguas no sincronizadas: resolver contrato por trabajador/obra/período.
            # El camino correcto ahora es que AnticipoDetalle ya venga con contrato_id.
            if not contrato_id and trabajador_id:
                q_contr = (
                    db.session.query(Contrato.id)
                    .filter(Contrato.trabajador_id == trabajador_id)
                    .filter(Contrato.fecha_inicio.isnot(None))
                    .filter(Contrato.fecha_inicio < periodo_fin)
                    .filter(func.coalesce(Contrato.fecha_termino, date(2999, 12, 31)) >= periodo_inicio)
                )
                if getattr(det, "obra_id", None):
                    q_contr = q_contr.filter(Contrato.obra_id == det.obra_id)

                ids = [r[0] for r in q_contr.order_by(Contrato.id.desc()).limit(5).all()]
                if len(ids) > 1:
                    current_app.logger.warning(
                        "Integración anticipos fallback: trabajador_id=%s sin contrato_id tiene múltiples contratos en período %s-%02d: %s (usando %s)",
                        trabajador_id, nomina.anio, nomina.mes, ids, ids[0]
                    )
                contrato_id = ids[0] if ids else None

            max_orden += 1

            item = SolicitudFondosItem(
                solicitud_id=solicitud.id,
                seccion="REMU",
                trabajador_id=trabajador_id,
                contrato_id=contrato_id,
                monto=det.monto or 0,
                orden=max_orden,

                # Origen / trazabilidad
                anticipo_nomina_id=nomina.id,
                anticipo_detalle_id=det.id,
                concepto="ANTICIPOS",
                descripcion=f"Anticipo de remuneraciones ({int(nomina.anio):04d}-{int(nomina.mes):02d})",
                control_interno=f"ANTICIPO_NOMINA_{nomina.id}",
            )

            db.session.add(item)
            db.session.flush()

            # Marcar detalle como integrado (si existen columnas)
            if hasattr(det, "integrado_sf_item_id"):
                det.integrado_sf_item_id = int(item.id)
            if hasattr(det, "integrado_en"):
                det.integrado_en = datetime.utcnow()
            if hasattr(det, "integrado_por"):
                det.integrado_por = current_user.id

            insertados += 1

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f"Error integrando anticipos a SF: {e}", "danger")
        return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))

    if wipe and deleted > 0:
        flash(f"🧹 Se eliminaron {deleted} ítems de anticipos (esta nómina) antes de reintegrar.", "info")

    if estado_nom == "BORRADOR":
        flash("⚠️ Integración realizada desde nómina en BORRADOR (vista previa para jefatura).", "warning")

    flash(f"Integración completada ✅ Insertados: {insertados} · Omitidos (ya estaban): {omitidos}.", "success")
    return redirect(url_for("anticipos.detalle", nomina_id=nomina.id))


# ---------------------------
# Imprimible (HTML)
# ---------------------------
@bp.get("/<int:nomina_id>/imprimir")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
def imprimir(nomina_id: int):
    nomina = AnticipoNomina.query.get_or_404(nomina_id)
    _require_nomina_access(nomina)

    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    if nomina_prev:
        _require_nomina_access(nomina_prev)

    nomina_prev_id = nomina_prev.id if nomina_prev else None
    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    PrevDet = aliased(AnticipoDetalle)
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)
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
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(ContratoV, ContratoV.id == AnticipoDetalle.contrato_id)
        .outerjoin(Cargo, Cargo.id == func.coalesce(ContratoV.cargo_id, Trabajador.cargo_id))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
                # Ideal: mismo contrato. Compatibilidad: nóminas antiguas sin contrato_id.
                (
                    (PrevDet.contrato_id == AnticipoDetalle.contrato_id)
                    | (PrevDet.contrato_id.is_(None))
                    | (AnticipoDetalle.contrato_id.is_(None))
                ),
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

    observaciones_list = []
    obs_counter = 1

    detalles = []
    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        obs_ref = None
        obs_text = (d.observacion or "").strip()

        if obs_text:
            obs_ref = obs_counter
            observaciones_list.append({
                "n": obs_counter,
                "rut": _rut_con_puntos(getattr(d, "rut", None)) or "-",
                "nombre": nombre_ordenado,
                "monto": float(d.monto or 0),
                "observacion": obs_text,
            })
            obs_counter += 1

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "rut_fmt": _rut_con_puntos(getattr(d, "rut", None)) or (getattr(d, "rut", None) or "-"),
                "obs_ref": obs_ref,
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
        observaciones_list=observaciones_list,
    )

@bp.get("/<int:nomina_id>/imprimir.pdf")
@login_required
@role_required("ADMIN", "OPERADOR", "REVISOR")
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
    _require_nomina_access(nomina)

    anio_prev, mes_prev = _prev_period(nomina.anio, nomina.mes)
    nomina_prev = AnticipoNomina.query.filter_by(
        anio=anio_prev, mes=mes_prev, centro_costo=nomina.centro_costo
    ).first()
    if nomina_prev:
        _require_nomina_access(nomina_prev)

    nomina_prev_id = nomina_prev.id if nomina_prev else None
    periodo_prev_str = f"{anio_prev:04d}-{mes_prev:02d}"

    PrevDet = aliased(AnticipoDetalle)
    monto_prev_expr = func.coalesce(PrevDet.monto, 0) if nomina_prev_id else literal(0)
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
        )
        .outerjoin(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        .outerjoin(ContratoV, ContratoV.id == AnticipoDetalle.contrato_id)
        .outerjoin(Cargo, Cargo.id == func.coalesce(ContratoV.cargo_id, Trabajador.cargo_id))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
    )

    if nomina_prev_id:
        q = q.outerjoin(
            PrevDet,
            and_(
                PrevDet.nomina_id == nomina_prev_id,
                PrevDet.trabajador_id == AnticipoDetalle.trabajador_id,
                # Ideal: mismo contrato. Compatibilidad: nóminas antiguas sin contrato_id.
                (
                    (PrevDet.contrato_id == AnticipoDetalle.contrato_id)
                    | (PrevDet.contrato_id.is_(None))
                    | (AnticipoDetalle.contrato_id.is_(None))
                ),
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

    observaciones_list = []
    obs_counter = 1

    detalles = []
    for d, cargo_nombre, tipo_trabajador, ap_paterno, ap_materno, nombres, monto_prev in rows:
        nombre_ordenado = " ".join(
            p for p in [ap_paterno, ap_materno, nombres] if p and str(p).strip()
        ).strip()
        if not nombre_ordenado:
            nombre_ordenado = (d.nombre_completo or "-").strip()

        obs_ref = None
        obs_text = (d.observacion or "").strip()

        if obs_text:
            obs_ref = obs_counter
            observaciones_list.append({
                "n": obs_counter,
                "rut": format_rut(getattr(d, "rut", None)),
                "nombre": nombre_ordenado,
                "monto": float(d.monto or 0),
                "observacion": obs_text,
            })
            obs_counter += 1

        detalles.append(
            {
                "d": d,
                "cargo_nombre": cargo_nombre or "-",
                "tipo_trabajador": (tipo_trabajador or "SIN TIPO").strip(),
                "monto_prev": float(monto_prev or 0),
                "nombre_ordenado": nombre_ordenado,
                "rut_fmt": format_rut(getattr(d, "rut", None)),
                "obs_ref": obs_ref,
            }
        )

    total_monto = (
        db.session.query(func.coalesce(func.sum(AnticipoDetalle.monto), 0))
        .filter(AnticipoDetalle.nomina_id == nomina.id)
        .scalar()
    )

    try:
        html = render_template(
            "anticipos/anticipos_imprimir_pdf.html",
            nomina=nomina,
            detalles=detalles,
            total_monto=total_monto,
            nomina_prev=nomina_prev,
            periodo_prev_str=periodo_prev_str,
            observaciones_list=observaciones_list,
        )
    except TemplateError as e:
        flash(f"Error template impresión PDF: {e}", "error")
        return redirect(url_for("anticipos.imprimir", nomina_id=nomina_id))

    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    periodo_label = f"{nomina.anio:04d}-{nomina.mes:02d}"
    cc_label = (nomina.centro_costo or "SIN_CC").strip()
    filename = f"{periodo_label} Nómina Anticipos - {cc_label}.pdf"
    filename = "".join(ch for ch in filename if ch not in '\\/:*?"<>|').strip() or "Nomina_Anticipos.pdf"

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'

    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Surrogate-Control"] = "no-store"

    return resp

import csv
from io import StringIO

@bp.get("/edig")
@login_required
@role_required("ADMIN")
def edig():
    # 1) Preferir última nómina VISADA
    last_visada = (
        db.session.query(AnticipoNomina.anio, AnticipoNomina.mes)
        .filter(AnticipoNomina.estado == "VISADA")
        .order_by(AnticipoNomina.anio.desc(), AnticipoNomina.mes.desc())
        .first()
    )

    # 2) Si no hay VISADA, usar la última nómina existente (cualquier estado)
    last_any = None
    if not last_visada:
        last_any = (
            db.session.query(AnticipoNomina.anio, AnticipoNomina.mes)
            .order_by(AnticipoNomina.anio.desc(), AnticipoNomina.mes.desc(), AnticipoNomina.id.desc())
            .first()
        )

    if last_visada:
        default_periodo = f"{int(last_visada.anio):04d}-{int(last_visada.mes):02d}"
    elif last_any:
        default_periodo = f"{int(last_any[0]):04d}-{int(last_any[1]):02d}"
    else:
        now = datetime.now()
        default_periodo = f"{now.year:04d}-{now.month:02d}"


    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    token = (request.args.get("t") or "").strip()
    resultado = _load_edig_meta(token) if token else None

    return render_template(
        "anticipos/anticipos_edig.html",
        default_periodo=default_periodo,
        empleadores=empleadores,
        resultado=resultado,
        selected_periodo=(resultado.get("periodo") if resultado else None),
        selected_empresa_id=(resultado.get("empresa_id") if resultado else None),
    )


@bp.get("/edig/descargar/<token>")
@login_required
@role_required("ADMIN")
def edig_descargar(token: str):
    meta = _load_edig_meta(token)
    if not meta:
        flash("No se encontró el archivo temporal. Genera nuevamente.", "warning")
        return redirect(url_for("anticipos.edig"))

    if not meta.get("download_token"):
        flash("Esta exportación no tiene CSV (no hay filas exportables).", "warning")
        return redirect(url_for("anticipos.edig", t=token))

    found = _find_csv_by_token(token)
    if not found:
        flash("No se encontró el archivo temporal. Genera nuevamente.", "warning")
        return redirect(url_for("anticipos.edig", t=token))

    path, filename = found
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv; charset=utf-8",
        conditional=True,
    )




from sqlalchemy.orm import aliased
import csv
from io import StringIO

@bp.post("/edig/generar")
@login_required
@role_required("ADMIN")
def edig_generar():
    from datetime import date

    periodo = (request.form.get("periodo") or "").strip()  # YYYY-MM
    empresa_id = _to_int(request.form.get("empresa_id"))

    if not periodo or "-" not in periodo:
        flash("Período inválido. Usa formato YYYY-MM (ej: 2026-01).", "warning")
        return redirect(url_for("anticipos.edig"))

    if not empresa_id:
        flash("Selecciona una empresa.", "warning")
        return redirect(url_for("anticipos.edig"))

    try:
        anio = int(periodo.split("-")[0])
        mes = int(periodo.split("-")[1])
    except Exception:
        flash("Período inválido. Usa formato YYYY-MM (ej: 2026-01).", "warning")
        return redirect(url_for("anticipos.edig"))

    empresa = Empleador.query.get(empresa_id)
    if not empresa:
        flash("Empresa no encontrada.", "warning")
        return redirect(url_for("anticipos.edig"))

    # Rango del período
    periodo_inicio = date(anio, mes, 1)
    periodo_fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)

    q = (
        db.session.query(AnticipoDetalle, Trabajador, Contrato)
        .join(AnticipoNomina, AnticipoNomina.id == AnticipoDetalle.nomina_id)
        .join(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        # Fuente de verdad: cada línea de anticipo apunta a SU contrato.
        # Esto evita volver a resolver por trabajador y perder el segundo contrato.
        .outerjoin(Contrato, Contrato.id == AnticipoDetalle.contrato_id)
        .filter(AnticipoNomina.anio == anio, AnticipoNomina.mes == mes)
        .filter(AnticipoNomina.estado == "VISADA")
        .filter(Contrato.empleador_id == empresa_id)
        .filter(func.coalesce(AnticipoDetalle.monto, 0) > 0)
        .order_by(
            func.coalesce(Trabajador.ap_paterno, "").asc(),
            func.coalesce(Trabajador.ap_materno, "").asc(),
            func.coalesce(Trabajador.nombres, "").asc(),
            Contrato.fecha_inicio.asc(),
            AnticipoDetalle.contrato_id.asc(),
            AnticipoDetalle.id.asc(),
        )
    )

    rows = q.all()
    if not rows:
        flash("No se encontraron anticipos VISADOS para ese período.", "info")
        return redirect(url_for("anticipos.edig"))

    output = StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["RUT", "Nombre Trabajador", "Nro. Contrato", "Codigo de Haber o Dscto.", "Monto"])

    excluidos = []
    ok_count = 0
    total_monto = 0.0
    total_count = 0

    contrato_ids_export = [int(c.id) for _det, _t, c in rows if c is not None and getattr(c, "id", None)]
    nro_contrato_por_id = _build_nros_contrato_edig(contrato_ids_export, periodo_inicio, periodo_fin)

    for det, t, contrato in rows:
        total_count += 1
        contrato_id = int(contrato.id) if contrato is not None and getattr(contrato, "id", None) else None
        nro_contrato_edig = nro_contrato_por_id.get(contrato_id, 1) if contrato_id else None

        monto = float(getattr(det, "monto", 0) or 0)
        monto_int = int(round(monto))

        rut = _rut_trabajador_para_edig(t, det) or ""
        nombre = _format_nombre_completo(t) or (getattr(det, "nombre_completo", None) or "")
        nombre = " ".join(nombre.split()).strip()

        if monto_int <= 0:
            excluidos.append({"rut": rut, "nombre": nombre, "monto": monto_int, "motivo": "MONTO_CERO"})
            continue

        if not contrato_id:
            excluidos.append({"rut": rut, "nombre": nombre, "monto": monto_int, "motivo": "SIN_CONTRATO_EN_PERIODO"})
            continue

        if not nro_contrato_edig:
            excluidos.append({"rut": rut, "nombre": nombre, "monto": monto_int, "contrato_id": contrato_id, "motivo": "SIN_NRO_CONTRATO_EDIG"})
            continue

        if not rut.strip() or "-" not in rut:
            excluidos.append({"rut": rut, "nombre": nombre, "monto": monto_int, "motivo": "SIN_RUT"})
            continue

        writer.writerow([rut, nombre, str(nro_contrato_edig), "DANTICIPOS", str(monto_int)])
        ok_count += 1
        total_monto += float(monto_int)

    # Guardar siempre meta + excluidos, aunque ok_count sea 0 (para mostrar detalle)
    token = uuid.uuid4().hex
    tmp_dir = _tmp_edig_dir()

    periodo_label = f"{anio:04d}-{mes:02d}"
    filename_csv = _safe_filename(f"{periodo_label} Anticipos - {empresa.razon_social}.csv")

    path_csv = os.path.join(tmp_dir, f"{token}_{filename_csv}")

    path_excl = os.path.join(tmp_dir, f"{token}_excluidos.json")
    path_meta = _meta_path(token)

    # CSV (solo si hay ok_count > 0)
    if ok_count > 0:
        csv_bytes = output.getvalue().encode("utf-8-sig")
        with open(path_csv, "wb") as f:
            f.write(csv_bytes)

    with open(path_excl, "w", encoding="utf-8") as f:
        json.dump(excluidos, f, ensure_ascii=False, indent=2)

    meta = {
        "periodo": periodo,
        "empresa_id": empresa_id,
        "empresa_label": empresa.razon_social,
        "ok_count": ok_count,
        "total_monto": float(total_monto or 0),
        "excluidos_count": len(excluidos),
        "total_count": total_count,
        "download_token": token if ok_count > 0 else None,
    }
    with open(path_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if ok_count == 0:
        flash("No hay filas exportables (revisa el detalle de excluidos).", "warning")
    else:
        flash("CSV generado correctamente.", "success")

    # ✅ redirect pro: token via querystring (sin session)
    return redirect(url_for("anticipos.edig", t=token))



@bp.get("/edig/excluidos/<token>")
@login_required
@role_required("ADMIN")
def edig_excluidos(token: str):
    path = _find_excluidos_by_token(token)
    if not path:
        return {"error": "Archivo de excluidos no encontrado"}, 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {"excluidos": data}





# ---------------------------
# Nóminas bancarias (XLSX)
# ---------------------------
@bp.get("/nominas_banco")
@login_required
@role_required("ADMIN")
def nominas_banco():
    last_visada = (
        db.session.query(AnticipoNomina.anio, AnticipoNomina.mes)
        .filter(AnticipoNomina.estado == "VISADA")
        .order_by(AnticipoNomina.anio.desc(), AnticipoNomina.mes.desc())
        .first()
    )

    if last_visada:
        default_periodo = f"{last_visada.anio:04d}-{last_visada.mes:02d}"
    else:
        now = datetime.now()
        default_periodo = f"{now.year:04d}-{now.month:02d}"

    empleadores = Empleador.query.order_by(Empleador.razon_social.asc()).all()

    q_obras = Obra.query.order_by(Obra.nombre.asc())
    if not current_user.has_role("ADMIN"):
        obra_ids_user = [o.id for o in (current_user.obras or [])]
        if obra_ids_user:
            q_obras = q_obras.filter(Obra.id.in_(obra_ids_user))
        else:
            q_obras = q_obras.filter(literal(False))

    obras = q_obras.all()

    form = {
        "plantilla": (request.args.get("plantilla") or "PAGOS_REMUN").strip(),
        "periodo": (request.args.get("periodo") or "").strip(),
        "empresa_ids": [],
        "obra_ids": [],
    }

    raw_emp_ids = request.args.get("empresa_ids") or ""
    form["empresa_ids"] = [_to_int(x) for x in raw_emp_ids.split(",") if _to_int(x)]

    raw_obra_ids = request.args.get("obra_ids") or ""
    form["obra_ids"] = [_to_int(x) for x in raw_obra_ids.split(",") if _to_int(x)]

    resultado = session.pop("nomina_banco_resultado", None)

    return render_template(
        "anticipos/anticipos_nominas_banco.html",
        obras=obras,
        empleadores=empleadores,
        default_periodo=default_periodo,
        form=form,
        resultado=resultado,
    )


@bp.post("/nominas_banco/generar")
@login_required
@role_required("ADMIN")
def nominas_banco_generar():
    from ...services.bank_nominas import (
        TEMPLATE_PAGOS_REMUN,
        TEMPLATE_TRANSFER_MAS,
        aggregate_rows,
        build_bank_rows,
        build_xlsx_from_template,
        get_template_path,
    )

    def _get_any(d: object, keys: tuple[str, ...]) -> str | None:
        if isinstance(d, dict):
            for k in keys:
                v = d.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None
        for k in keys:
            if hasattr(d, k):
                v = getattr(d, k)
                if v is not None and str(v).strip():
                    return str(v).strip()
        return None

    def _parse_amount(v) -> float:
        try:
            if v is None:
                return 0.0
            if isinstance(v, (int, float)):
                return float(v)

            s = str(v).strip()
            if not s:
                return 0.0

            s = s.replace(" ", "").replace("$", "")
            has_dot = "." in s
            has_comma = "," in s

            if has_dot and has_comma:
                s = s.replace(".", "").replace(",", ".")
                return float(s)

            if has_comma and not has_dot:
                s = s.replace(",", ".")
                return float(s)

            if has_dot and not has_comma:
                left, right = s.split(".", 1)
                if right.isdigit() and len(right) == 3 and left.isdigit() and 1 <= len(left) <= 3:
                    s = s.replace(".", "")
                    return float(s)
                return float(s)

            return float(s)
        except Exception:
            return 0.0

    plantilla = (request.form.get("plantilla") or "PAGOS_REMUN").strip().upper()

    periodo = (request.form.get("periodo") or "").strip()  # YYYY-MM
    if not periodo:
        last_visada = (
            db.session.query(AnticipoNomina.anio, AnticipoNomina.mes)
            .filter(AnticipoNomina.estado == "VISADA")
            .order_by(AnticipoNomina.anio.desc(), AnticipoNomina.mes.desc())
            .first()
        )
        if last_visada:
            periodo = f"{int(last_visada[0]):04d}-{int(last_visada[1]):02d}"
        else:
            now = datetime.now()
            periodo = f"{now.year:04d}-{now.month:02d}"

    empresa_ids_int = [_to_int(x) for x in request.form.getlist("empresa_ids")]
    empresa_ids_int = [x for x in empresa_ids_int if x]

    obra_ids_int = [_to_int(x) for x in request.form.getlist("obra_ids")]
    obra_ids_int = [x for x in obra_ids_int if x]

    if not periodo or "-" not in periodo:
        flash("Período inválido. Usa formato YYYY-MM.", "warning")
        return redirect(url_for("anticipos.nominas_banco"))

    try:
        anio = int(periodo.split("-")[0])
        mes = int(periodo.split("-")[1])
    except Exception:
        flash("Período inválido. Usa formato YYYY-MM.", "warning")
        return redirect(url_for("anticipos.nominas_banco"))

    if plantilla not in {"PAGOS_REMUN", "TRANSFER_MAS"}:
        flash("Plantilla inválida.", "warning")
        return redirect(url_for("anticipos.nominas_banco"))

    qs_empresa_ids = ",".join(str(x) for x in empresa_ids_int) if empresa_ids_int else ""
    qs_obra_ids = ",".join(str(x) for x in obra_ids_int) if obra_ids_int else ""

    empresas_label = None
    if empresa_ids_int:
        rows_emp = (
            db.session.query(Empleador.razon_social)
            .filter(Empleador.id.in_(empresa_ids_int))
            .order_by(Empleador.razon_social.asc())
            .all()
        )
        labels = [r[0] for r in rows_emp if r and r[0]]
        empresas_label = ", ".join(labels) if labels else None

    q = (
        db.session.query(AnticipoDetalle, Trabajador, Banco)
        .join(AnticipoNomina, AnticipoNomina.id == AnticipoDetalle.nomina_id)
        .join(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
        # Clave del arreglo: la línea de anticipo pertenece a UN contrato.
        # Antes se unía por trabajador y contrato vigente, lo que hacía que el sistema
        # eligiera/duplicara contratos de forma implícita.
        .outerjoin(Contrato, Contrato.id == AnticipoDetalle.contrato_id)
        .outerjoin(Banco, Banco.id == Trabajador.banco_id)
        .filter(AnticipoNomina.anio == anio, AnticipoNomina.mes == mes)
        .filter(AnticipoNomina.estado == "VISADA")
        .filter(func.coalesce(AnticipoDetalle.monto, 0) > 0)
    )

    if empresa_ids_int:
        q = q.filter(Contrato.empleador_id.in_(empresa_ids_int))

    if obra_ids_int:
        q = q.filter(AnticipoDetalle.obra_id.in_(obra_ids_int))

    detalles_rows = q.all()

    if not detalles_rows:
        flash("No se encontraron anticipos VISADOS para el período y filtro seleccionado.", "info")
        return redirect(
            url_for(
                "anticipos.nominas_banco",
                periodo=periodo,
                plantilla=plantilla,
                empresa_ids=qs_empresa_ids,
                obra_ids=qs_obra_ids,
            )
        )

    build = build_bank_rows(detalles_rows)
    ok_rows = aggregate_rows(build.ok_rows)

    if not ok_rows:
        session["nomina_banco_resultado"] = {
            "periodo": periodo,
            "plantilla": plantilla,
            "plantilla_label": (
                "Pagos Masivos Remuneraciones Santander"
                if plantilla == "PAGOS_REMUN"
                else "Transferencias Masivas Santander"
            ),
            "empresa_ids": empresa_ids_int,
            "empresas_label": empresas_label,
            "ok_count": 0,
            "obras_count": 0,
            "total_monto": 0,
            "excluidos_count": len(build.excluidos),
            "excluidos": build.excluidos[:200],
            "download_token": None,
        }
        flash("No hay registros exportables (revisa excluidos).", "warning")
        return redirect(
            url_for(
                "anticipos.nominas_banco",
                periodo=periodo,
                plantilla=plantilla,
                empresa_ids=qs_empresa_ids,
                obra_ids=qs_obra_ids,
            )
        )

    obras_count = 0
    try:
        obras_count = (
            db.session.query(func.count(func.distinct(AnticipoDetalle.obra_id)))
            .join(AnticipoNomina, AnticipoNomina.id == AnticipoDetalle.nomina_id)
            .join(Trabajador, Trabajador.id == AnticipoDetalle.trabajador_id)
            .outerjoin(Contrato, Contrato.id == AnticipoDetalle.contrato_id)
            .filter(AnticipoNomina.anio == anio, AnticipoNomina.mes == mes)
            .filter(AnticipoNomina.estado == "VISADA")
            .filter(Contrato.empleador_id.in_(empresa_ids_int) if empresa_ids_int else literal(True))
            .filter(AnticipoDetalle.obra_id.in_(obra_ids_int) if obra_ids_int else literal(True))
            .scalar()
        ) or 0
    except Exception:
        obras_count = 0

    total_monto = 0.0
    for r in ok_rows:
        monto_raw = _get_any(r, ("monto", "monto_pagado", "valor", "importe", "amount", "monto_total"))
        total_monto += _parse_amount(monto_raw)

    if plantilla == "PAGOS_REMUN":
        template_file = TEMPLATE_PAGOS_REMUN
        plantilla_label = "Pagos Masivos Remuneraciones Santander"
    else:
        template_file = TEMPLATE_TRANSFER_MAS
        plantilla_label = "Transferencias Masivas Santander"

    template_path = get_template_path(current_app.root_path, template_file)
    if not os.path.exists(template_path):
        flash(f"No se encontró la plantilla XLSX: {template_file}.", "error")
        return redirect(
            url_for(
                "anticipos.nominas_banco",
                periodo=periodo,
                plantilla=plantilla,
                empresa_ids=qs_empresa_ids,
                obra_ids=qs_obra_ids,
            )
        )

    try:
        wb = build_xlsx_from_template(
            template_path=template_path,
            template_kind=plantilla,
            rows=ok_rows,
            anio=anio,
            mes=mes,
        )
    except Exception as e:
        flash(f"Error construyendo XLSX: {e}", "error")
        return redirect(
            url_for(
                "anticipos.nominas_banco",
                periodo=periodo,
                plantilla=plantilla,
                empresa_ids=qs_empresa_ids,
                obra_ids=qs_obra_ids,
            )
        )

    token = uuid.uuid4().hex
    tmp_dir = os.path.join(current_app.instance_path, "tmp_nominas_banco")
    os.makedirs(tmp_dir, exist_ok=True)

    filename = f"nomina_{plantilla.lower()}_{anio:04d}-{mes:02d}.xlsx".replace(" ", "_")
    file_path = os.path.join(tmp_dir, f"{token}_{filename}")
    wb.save(file_path)

    files = session.get("nomina_banco_files", {}) or {}
    files[token] = {"path": file_path, "filename": filename}
    if len(files) > 5:
        for k in list(files.keys())[:-5]:
            files.pop(k, None)
    session["nomina_banco_files"] = files

    session["nomina_banco_resultado"] = {
        "periodo": periodo,
        "plantilla": plantilla,
        "plantilla_label": plantilla_label,
        "empresa_ids": empresa_ids_int,
        "empresas_label": empresas_label,
        "ok_count": len(ok_rows),
        "obras_count": int(obras_count or 0),
        "total_monto": float(total_monto or 0),
        "excluidos_count": len(build.excluidos),
        "excluidos": build.excluidos[:200],
        "download_token": token,
    }

    return redirect(
        url_for(
            "anticipos.nominas_banco",
            periodo=periodo,
            plantilla=plantilla,
            empresa_ids=qs_empresa_ids,
            obra_ids=qs_obra_ids,
        )
    )


@bp.get("/nominas_banco/descargar/<token>")
@login_required
@role_required("ADMIN")
def nominas_banco_descargar(token: str):
    files = session.get("nomina_banco_files", {}) or {}
    meta = files.get(token)

    if not meta:
        flash(
            "El archivo ya no está disponible (token expirado o sesión distinta). Genera la nómina nuevamente.",
            "warning",
        )
        return redirect(url_for("anticipos.nominas_banco"))

    path = meta.get("path")
    filename = meta.get("filename") or "nomina.xlsx"

    if not path or not os.path.exists(path):
        flash("No se encontró el archivo temporal. Genera la nómina nuevamente.", "warning")
        return redirect(url_for("anticipos.nominas_banco"))

    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        conditional=True,
    )
