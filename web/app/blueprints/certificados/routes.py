# web/app/blueprints/certificados/routes.py
from __future__ import annotations

import re
from datetime import datetime, timezone, date
from pathlib import Path

from flask import current_app, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required

from ...extensions import db
from ...models import CertificadoLaboral, Trabajador
from ...services.paths_nextcloud import get_nc_paths
from ...services.storage_nextcloud_fs import ensure_dir
from ...services.pdf_convert import convert_docx_to_pdf
from ...utils import parse_int

from ...services.certificados_docs import build_certif_antiguedad_docx

import sqlalchemy as sa

from . import bp


# ---------------------------
# Constantes MVP
# ---------------------------

_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
TIPOS_CERT = ["ANTIGUEDAD", "VIGENCIA", "OTRO"]
ESTADOS_CERT = ["BORRADOR", "EMITIDO", "ANULADO"]


# ---------------------------
# Helpers MVP
# ---------------------------

def _clean_filename(s: str) -> str:
    s = (s or "").strip()
    s = _INVALID_FS_CHARS_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "SIN_NOMBRE"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_user() -> str:
    return str(getattr(current_user, "username", None) or getattr(current_user, "id", None) or "unknown")


def _push_meta(cert: CertificadoLaboral, key: str, payload: dict) -> None:
    meta = (cert.meta or {}) if hasattr(cert, "meta") else {}
    current = meta.get(key)
    entry = {"at": _now_utc_iso(), "by": _audit_user(), **payload}

    if current is None:
        meta[key] = [entry]
    elif isinstance(current, list):
        current.append(entry)
        meta[key] = current
    else:
        meta[key] = [current, entry]

    cert.meta = meta


def _cert_target_dir(cert: CertificadoLaboral) -> Path:
    """
    Carpeta destino Nextcloud FS:
    /<CENTRO_COSTO>/Laboral/Trabajadores/<Apellido Apellido Nombres>/CERTIFICADOS/
    - Centro de costo: desde obra del certificado; fallback a obra del contrato.
    """
    t = cert.trabajador
    obra = (
        cert.obra
        or (cert.contrato.obra if cert.contrato else None)
        or getattr(cert.trabajador, "obra", None)
    )


    centro_costo = (getattr(obra, "centro_costo", "") or "").strip() if obra else ""
    if not centro_costo:
        raise RuntimeError("No se pudo determinar el centro de costo (obras.centro_costo).")

    nc = get_nc_paths()
    return nc.dir_trabajador(
        centro_costo=centro_costo,
        nombres=t.nombres or "",
        ap_paterno=t.ap_paterno or "",
        ap_materno=t.ap_materno or "",
        tipo_doc="CERTIFICADOS",
    )


def _cert_base_filename(cert: CertificadoLaboral) -> str:
    """
    Ej:
    2026-01-30 Certificado Antigüedad - Apellido Apellido Nombres (Objetivo)
    """
    t = cert.trabajador
    fecha_iso = cert.fecha_emision.isoformat() if cert.fecha_emision else date.today().isoformat()

    nombre = f"{t.ap_paterno or ''} {t.ap_materno or ''} {t.nombres or ''}".strip()
    tipo = (cert.tipo or "").strip().upper()

    if tipo == "ANTIGUEDAD":
        tipo_txt = "Certificado Antigüedad"
    elif tipo == "VIGENCIA":
        tipo_txt = "Certificado Vigencia"
    else:
        tipo_txt = "Certificado"

    obj = (cert.objetivo or "").strip()
    if obj:
        base = f"{fecha_iso} {tipo_txt} - {nombre} ({obj})"
    else:
        base = f"{fecha_iso} {tipo_txt} - {nombre}"

    return _clean_filename(base)


def _rut_digits(s: str) -> str:
    s = (s or "").replace(".", "").replace("-", "").strip()
    return re.sub(r"\D+", "", s)


# ---------------------------
# Listado
# ---------------------------

@bp.get("/")
@login_required
def listado():
    q = (request.args.get("q") or "").strip()
    tipo = (request.args.get("tipo") or "").strip().upper()
    estado = (request.args.get("estado") or "").strip().upper()

    query = CertificadoLaboral.query

    if tipo:
        query = query.filter(CertificadoLaboral.tipo == tipo)

    if estado:
        query = query.filter(CertificadoLaboral.estado == estado)

    if q:
        digits = _rut_digits(q)

        # join trabajador para buscar por nombre/rut
        query = query.join(CertificadoLaboral.trabajador)

        # Si parece RUT => match por rut numérico
        if digits and len(digits) >= 6:
            rut_num = parse_int(digits)
            if rut_num:
                query = query.filter(CertificadoLaboral.trabajador.has(rut=rut_num))
        else:
            like = f"%{q}%"
            query = query.filter(
                (CertificadoLaboral.objetivo.ilike(like))
                | (CertificadoLaboral.trabajador.has(Trabajador.nombres.ilike(like)))
                | (CertificadoLaboral.trabajador.has(Trabajador.ap_paterno.ilike(like)))
                | (CertificadoLaboral.trabajador.has(Trabajador.ap_materno.ilike(like)))
            )

    certs = query.order_by(CertificadoLaboral.id.desc()).limit(200).all()

    # KPIs (dashboard)
    kpis = {
        "BORRADOR": CertificadoLaboral.query.filter(CertificadoLaboral.estado == "BORRADOR").count(),
        "EMITIDO": CertificadoLaboral.query.filter(CertificadoLaboral.estado == "EMITIDO").count(),
        "ANULADO": CertificadoLaboral.query.filter(CertificadoLaboral.estado == "ANULADO").count(),
    }

    return render_template(
        "certificados/listado.html",
        certificados=certs,
        q=q,
        tipo=tipo,
        estado=estado,
        TIPOS_CERT=TIPOS_CERT,
        ESTADOS_CERT=ESTADOS_CERT,
        kpis=kpis,
    )


# ---------------------------
# Nuevo + Crear
# ---------------------------

@bp.get("/nuevo")
@login_required
def nuevo():
    q = (request.args.get("q") or "").strip()
    trabajadores: list[Trabajador] = []

    if q:
        digits = _rut_digits(q)
        query = Trabajador.query

        # RUT directo
        if digits and len(digits) >= 6:
            rut_num = parse_int(digits)
            if rut_num:
                query = query.filter(Trabajador.rut == rut_num)
        else:
            # búsqueda por tokens AND
            tokens = [t for t in re.split(r"\s+", q) if t]
            for tok in tokens:
                like = f"%{tok}%"
                query = query.filter(
                    (Trabajador.nombres.ilike(like))
                    | (Trabajador.ap_paterno.ilike(like))
                    | (Trabajador.ap_materno.ilike(like))
                )

        trabajadores = query.order_by(Trabajador.ap_paterno.asc()).limit(50).all()

    return render_template(
        "certificados/nuevo.html",
        q=q,
        trabajadores=trabajadores,
        TIPOS_CERT=TIPOS_CERT,
        hoy=date.today().isoformat(),
    )

@bp.get("/api/trabajadores")
@login_required
def api_trabajadores():
    """
    Autocomplete trabajadores:
    - q: string (rut o nombres)
    Retorna: [{id, rut, label}]
    """
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    q_norm = q.replace(".", "").replace("-", "").strip()
    q_digits = re.sub(r"\D+", "", q_norm)

    query = Trabajador.query

    # Si parece RUT (solo números) => match por rut numérico
    if q_digits and len(q_digits) >= 6:
        rut_num = parse_int(q_digits)
        if rut_num:
            query = query.filter(Trabajador.rut == rut_num)
        else:
            return jsonify([])
    else:
        # tokens AND en nombres/apellidos
        tokens = [t for t in re.split(r"\s+", q) if t]
        for tok in tokens:
            like = f"%{tok}%"
            query = query.filter(
                sa.or_(
                    Trabajador.nombres.ilike(like),
                    Trabajador.ap_paterno.ilike(like),
                    Trabajador.ap_materno.ilike(like),
                )
            )

    # Orden corporativo 😄
    trabajadores = query.order_by(
        Trabajador.ap_paterno.asc(),
        Trabajador.ap_materno.asc(),
        Trabajador.nombres.asc(),
    ).limit(15).all()

    payload = []
    for t in trabajadores:
        rut = getattr(t, "rut_completo", None) or f"{getattr(t,'rut','')}-{getattr(t,'dv','')}"
        label = f"{rut} · {t.ap_paterno or ''} {t.ap_materno or ''}, {t.nombres or ''}".strip()
        payload.append({"id": t.id, "rut": rut, "label": label})

    return jsonify(payload)


@bp.post("/crear")
@login_required
def crear():
    trabajador_id = parse_int(request.form.get("trabajador_id"))
    tipo = (request.form.get("tipo") or "ANTIGUEDAD").strip().upper()
    objetivo = (request.form.get("objetivo") or "").strip() or None

    fecha_raw = (request.form.get("fecha_emision") or "").strip()
    try:
        fecha_emision = date.fromisoformat(fecha_raw) if fecha_raw else date.today()
    except Exception:
        fecha_emision = date.today()

    if not trabajador_id:
        flash("Debes seleccionar un trabajador.", "warning")
        return redirect(url_for("certificados.nuevo"))

    if tipo not in TIPOS_CERT:
        tipo = "ANTIGUEDAD"

    trabajador = Trabajador.query.get_or_404(trabajador_id)

    # Contrato preferente: VIGENTE más reciente; si no hay, el más reciente
    contrato_pref = None
    if trabajador.contratos:
        vigentes = [c for c in trabajador.contratos if (c.estado_contrato or "").upper() == "VIGENTE"]
        base = vigentes if vigentes else list(trabajador.contratos)

        contrato_pref = sorted(
            base,
            key=lambda c: (c.fecha_inicio or date.min),
            reverse=True,
        )[0]

    # Resolver obra_id con fallback robusto
    obra_id = None
    if contrato_pref and getattr(contrato_pref, "obra_id", None):
        obra_id = contrato_pref.obra_id
    else:
        obra_id = getattr(trabajador, "obra_id", None)

    # Resolver empleador_id con fallback robusto
    empleador_id = None
    if contrato_pref and getattr(contrato_pref, "empleador_id", None):
        empleador_id = contrato_pref.empleador_id
    else:
        emp_pref = getattr(trabajador, "empleador_preferente", None)
        empleador_id = getattr(emp_pref, "id", None) if emp_pref else None

    cert = CertificadoLaboral(
        trabajador_id=trabajador.id,
        tipo=tipo,
        objetivo=objetivo,
        fecha_emision=fecha_emision,
        estado="BORRADOR",
        creado_por_user_id=getattr(current_user, "id", None),

        # Claves para que el generador siempre tenga insumos
        obra_id=obra_id,  # por tu modelo, debería venir siempre
        contrato_id=(contrato_pref.id if contrato_pref else None),
        empleador_id=empleador_id,
    )

    db.session.add(cert)
    db.session.commit()

    flash("Certificado creado (BORRADOR).", "success")
    return redirect(url_for("certificados.editar", certificado_id=cert.id))



# ---------------------------
# Editar + Guardar
# ---------------------------

@bp.get("/<int:certificado_id>/editar")
@login_required
def editar(certificado_id: int):
    cert = CertificadoLaboral.query.get_or_404(certificado_id)

    # MVP: Permitimos abrir cualquier estado, pero solo BORRADOR editable.
    if cert.estado != "BORRADOR":
        flash("Este certificado está en modo solo lectura (no está en BORRADOR).", "info")

    return render_template("certificados/editar.html", cert=cert, TIPOS_CERT=TIPOS_CERT)


@bp.post("/<int:certificado_id>/guardar")
@login_required
def guardar(certificado_id: int):
    cert = CertificadoLaboral.query.get_or_404(certificado_id)

    if cert.estado != "BORRADOR":
        flash("Solo puedes guardar cambios en BORRADOR.", "warning")
        return redirect(url_for("certificados.editar", certificado_id=cert.id))

    tipo = (request.form.get("tipo") or cert.tipo or "ANTIGUEDAD").strip().upper()
    if tipo not in TIPOS_CERT:
        tipo = cert.tipo or "ANTIGUEDAD"

    objetivo = (request.form.get("objetivo") or "").strip() or None

    cert.tipo = tipo
    cert.objetivo = objetivo

    _push_meta(cert, "edit", {"tipo": cert.tipo, "objetivo": cert.objetivo or ""})

    db.session.commit()
    flash("Cambios guardados.", "success")
    return redirect(url_for("certificados.editar", certificado_id=cert.id))


# ---------------------------
# Generar (PDF/DOCX/AMBOS)
# ---------------------------

@bp.route("/<int:certificado_id>/generar", methods=["GET", "POST"])
@login_required
def generar(certificado_id: int):
    cert = CertificadoLaboral.query.get_or_404(certificado_id)

    if cert.estado not in {"BORRADOR", "EMITIDO"}:
        flash("Solo puedes generar documentos en BORRADOR o EMITIDO.", "warning")
        return redirect(url_for("certificados.listado"))

    # Defaults (MVP): meta último config
    meta = cert.meta or {}
    last_inputs: dict = {}
    try:
        v = meta.get("cert_config")
        if isinstance(v, list) and v:
            last_inputs = (v[-1].get("inputs") or {}) if isinstance(v[-1], dict) else {}
    except Exception:
        last_inputs = {}

    # GET preselect formato desde querystring (para /emitir)
    formato_get = (request.args.get("formato") or "PDF").upper()

    # --- GET ---
    if request.method == "GET":
        vals = {
            "objetivo": (cert.objetivo or ""),
        }
        if isinstance(last_inputs, dict):
            vals.update({str(k): ("" if v is None else str(v)) for k, v in last_inputs.items()})

        return render_template(
            "certificados/certificado_generar.html",
            cert=cert,
            formato=formato_get if formato_get in ("DOCX", "PDF", "AMBOS") else "PDF",
            vals=vals,
            next_url=(request.args.get("next") or "").strip(),
        )

    # --- POST ---
    formato = (request.form.get("formato") or "PDF").upper()
    if formato not in ("DOCX", "PDF", "AMBOS"):
        formato = "PDF"

    # Compatibilidad: tu template usa name="objetivo"
    objetivo = (
        request.form.get("objetivo")
        or request.form.get("OBJETIVO")
        or request.form.get("CERTIFICADO_OBJETIVO")
        or ""
    ).strip()

    overrides: dict[str, str] = {
        "CERTIFICADO_OBJETIVO": objetivo,
    }

    # sincronizar objetivo al modelo (single source of truth)
    cert.objetivo = objetivo or None

    _push_meta(cert, "cert_config", {"formato": formato, "inputs": overrides})

    next_url = (request.form.get("next_url") or request.args.get("next") or "").strip()

    try:
        target_dir = _cert_target_dir(cert)
        ensure_dir(target_dir)

        base = _cert_base_filename(cert)
        docx_name = f"{base}.docx"
        pdf_name = f"{base}.pdf"

        docx_final = target_dir / docx_name
        pdf_final = target_dir / pdf_name

        out_tmp = Path(current_app.instance_path) / "generated_docs" / "certificados"
        ensure_dir(out_tmp)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        docx_tmp = out_tmp / f"tmp_cert_{cert.id}_{stamp}.docx"

        # Generación DOCX según tipo
        tipo = (cert.tipo or "").strip().upper()
        if tipo == "ANTIGUEDAD":
            build_certif_antiguedad_docx(cert, docx_tmp, overrides=overrides)
        else:
            raise RuntimeError(f"Tipo de certificado no implementado aún: {tipo}")

        # Guardado final
        if formato in ("DOCX", "AMBOS"):
            docx_final.write_bytes(docx_tmp.read_bytes())
            cert.docx_nombre = docx_name
            cert.docx_ruta = str(docx_final)

        if formato in ("PDF", "AMBOS"):
            pdf_tmp_dir = out_tmp / "pdf"
            ensure_dir(pdf_tmp_dir)
            pdf_tmp = convert_docx_to_pdf(docx_tmp, pdf_tmp_dir)
            pdf_final.write_bytes(pdf_tmp.read_bytes())
            cert.pdf_nombre = pdf_name
            cert.pdf_ruta = str(pdf_final)

        if cert.estado == "BORRADOR":
            cert.estado = "EMITIDO"

        _push_meta(
            cert,
            "doc_certificado",
            {
                "docx": str(docx_final) if formato in ("DOCX", "AMBOS") else "",
                "pdf": str(pdf_final) if formato in ("PDF", "AMBOS") else "",
                "formato": formato,
                "estado": cert.estado,
                "tipo": cert.tipo,
            },
        )

        db.session.commit()

        if formato == "DOCX":
            flash("Certificado generado y guardado en Nextcloud: DOCX", "success")
        elif formato == "PDF":
            flash("Certificado generado y guardado en Nextcloud: PDF", "success")
        else:
            flash("Certificado generado y guardado en Nextcloud: DOCX + PDF", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"No se pudo generar el certificado: {e}", "error")

    if next_url:
        return redirect(next_url)
    return redirect(url_for("certificados.listado"))


# ---------------------------
# Emitir / Anular (acciones rápidas desde listado)
# ---------------------------

@bp.post("/<int:certificado_id>/emitir")
@login_required
def emitir(certificado_id: int):
    cert = CertificadoLaboral.query.get_or_404(certificado_id)

    if cert.estado not in {"BORRADOR", "EMITIDO"}:
        flash("No puedes emitir este certificado por su estado.", "warning")
        return redirect(url_for("certificados.listado"))

    # Emitir = atajo a generar DOCX (conservador)
    return redirect(
        url_for(
            "certificados.generar",
            certificado_id=cert.id,
            formato="DOCX",
            next=url_for("certificados.editar", certificado_id=cert.id),
        )
    )


@bp.post("/<int:certificado_id>/anular")
@login_required
def anular(certificado_id: int):
    cert = CertificadoLaboral.query.get_or_404(certificado_id)

    if cert.estado == "ANULADO":
        flash("Este certificado ya está anulado.", "info")
        return redirect(url_for("certificados.listado"))

    cert.estado = "ANULADO"
    _push_meta(cert, "anulacion", {"motivo": "anulado_manual"})
    db.session.commit()

    flash("Certificado anulado.", "success")
    return redirect(url_for("certificados.listado"))
