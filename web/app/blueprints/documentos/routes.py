from flask import (
    render_template,
    redirect,
    url_for,
    request,
    flash,
)
from flask_login import login_required
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
from urllib.request import Request, urlopen
import re

from ...common.navigation import safe_next_url
from ...extensions import db
from ...models import Contrato, DocumentoLaboral
from ...config import DOCUMENTO_TIPOS
from ...utils import parse_date

from . import bp

# Si tienes role_required en tu proyecto, lo usamos.
# Si no existe, no rompemos el sistema.
try:
    from ...utils import role_required  # type: ignore
except Exception:  # pragma: no cover
    def role_required(*_args, **_kwargs):  # type: ignore
        def _decorator(fn):
            return fn
        return _decorator


def _validar_extension(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return "pdf"
    permitidas = {"pdf", "docx"}
    if ext not in permitidas:
        return "pdf"
    return ext



# -----------------------------------------------------------------------------
# Helpers documentos laborales · nombre real desde enlace externo / Nextcloud
# -----------------------------------------------------------------------------
def _normalizar_nombre_archivo(nombre: str | None) -> str | None:
    """Limpia un nombre de archivo detectado desde un enlace externo."""
    if not nombre:
        return None
    nombre = unquote(str(nombre)).replace("\\", "/").strip()
    nombre = nombre.split("?")[0].split("#")[0].rstrip("/")
    nombre = nombre.rsplit("/", 1)[-1].strip()
    if not nombre or nombre.lower() in {"download", "index.php", "s", "remote.php", "webdav"}:
        return None
    nombre = re.sub(r"[\r\n\t]+", " ", nombre).strip()
    nombre = re.sub(r"\s+", " ", nombre)
    return nombre[:255] if nombre else None


def _nombre_desde_content_disposition(header: str | None) -> str | None:
    """Extrae filename/filename* desde Content-Disposition."""
    header = header or ""
    if not header:
        return None

    # RFC 5987: filename*=UTF-8''archivo%20real.pdf
    match = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')?([^;]+)", header, flags=re.I)
    if match:
        return _normalizar_nombre_archivo(match.group(1).strip().strip('"'))

    match = re.search(r'filename\s*=\s*"([^"]+)"', header, flags=re.I)
    if match:
        return _normalizar_nombre_archivo(match.group(1))

    match = re.search(r"filename\s*=\s*([^;]+)", header, flags=re.I)
    if match:
        return _normalizar_nombre_archivo(match.group(1).strip().strip('"'))

    return None


def _download_url_nextcloud_public_share(enlace: str) -> str | None:
    """Convierte https://nextcloud.../s/TOKEN a https://nextcloud.../s/TOKEN/download."""
    try:
        parsed = urlparse(enlace)
    except Exception:
        return None

    partes = [p for p in parsed.path.split("/") if p]
    if "s" not in partes:
        return None

    idx = partes.index("s")
    if idx + 1 >= len(partes):
        return None

    token = partes[idx + 1]
    base_partes = partes[:idx]
    nueva_ruta = "/" + "/".join(base_partes + ["s", token, "download"])
    return urlunparse((parsed.scheme, parsed.netloc, nueva_ruta, "", "", ""))


def _extraer_nombre_archivo_desde_nextcloud_publico(enlace: str | None) -> str | None:
    """Consulta brevemente el enlace público de Nextcloud para leer Content-Disposition.

    Esto permite detectar nombres reales en enlaces tipo:
    https://nextcloud.grupo-cs.cl/s/TOKEN

    Se usa timeout corto para no dejar pegada la carga del formulario si Nextcloud
    no responde. Si falla, simplemente retorna None.
    """
    enlace = (enlace or "").strip()
    if not enlace:
        return None

    download_url = _download_url_nextcloud_public_share(enlace)
    if not download_url:
        return None

    for method in ("HEAD", "GET"):
        try:
            headers = {"User-Agent": "Sistema-Grupo-CS/1.0"}
            if method == "GET":
                headers["Range"] = "bytes=0-0"
            req = Request(download_url, headers=headers, method=method)
            with urlopen(req, timeout=5) as resp:  # nosec - URL ingresada por usuario autenticado
                nombre = _nombre_desde_content_disposition(resp.headers.get("Content-Disposition"))
                if nombre:
                    return nombre
        except Exception:
            continue

    return None


def _extraer_nombre_archivo_desde_enlace(enlace: str | None) -> str | None:
    """Obtiene el nombre visible del archivo desde un link directo o Nextcloud.

    Orden de resolución:
    1) Parámetros comunes: files, file, filename, name.
    2) Último segmento de la URL si parece archivo: *.pdf, *.docx, etc.
    3) Enlace público Nextcloud /s/TOKEN consultando /download y Content-Disposition.
    """
    enlace = (enlace or "").strip()
    if not enlace:
        return None

    parsed = urlparse(enlace)
    query = parse_qs(parsed.query)

    for key in ("files", "file", "filename", "name"):
        for valor in query.get(key) or []:
            nombre = _normalizar_nombre_archivo(valor)
            if nombre:
                return nombre

    for key in ("path", "dir"):
        for valor in query.get(key) or []:
            nombre = _normalizar_nombre_archivo(valor)
            if nombre and "." in nombre:
                return nombre

    nombre_path = _normalizar_nombre_archivo(parsed.path)
    if nombre_path and "." in nombre_path:
        return nombre_path

    return _extraer_nombre_archivo_desde_nextcloud_publico(enlace)


def _extension_desde_nombre_archivo(nombre: str | None) -> str | None:
    nombre = (nombre or "").strip()
    if "." not in nombre:
        return None
    return nombre.rsplit(".", 1)[-1].lower()

@bp.route("/contrato/<int:contrato_id>")
@login_required
@role_required("ADMIN")
def documentos_por_contrato(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)

    # Mapeo value -> label para mostrar el nombre bonito del tipo
    tipos_dict = dict(DOCUMENTO_TIPOS)

    # Nombre mostrable: prioriza el nombre real detectado desde el enlace.
    nombres_documentos = {
        doc.id: (_extraer_nombre_archivo_desde_enlace(doc.ruta_archivo) or doc.nombre_archivo)
        for doc in contrato.documentos
    }

    return render_template(
        "documentos/documentos_por_contrato.html",
        contrato=contrato,
        tipos_dict=tipos_dict,
        nombres_documentos=nombres_documentos,
    )


@bp.route("/contrato/<int:contrato_id>/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def nuevo_documento_contrato(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)

    # Permite preselección desde el botón del detalle:
    # /documentos/contrato/<id>/nuevo?tipo_documento=CONTRATO
    tipo_preseleccion = (request.args.get("tipo_documento") or "").strip() or None
    tipos_validos = {v for v, _label in DOCUMENTO_TIPOS}
    if tipo_preseleccion and tipo_preseleccion not in tipos_validos:
        tipo_preseleccion = None

    next_url = safe_next_url(request.args.get("next") or request.form.get("next"), fallback=None)

    if request.method == "POST":
        tipo = (request.form.get("tipo_documento") or "").strip()
        fecha_doc_raw = request.form.get("fecha_documento")  # puede venir vacío
        fecha_doc = parse_date(fecha_doc_raw) if fecha_doc_raw else None

        extension = _validar_extension(request.form.get("extension") or "pdf")
        enlace_nextcloud = (request.form.get("enlace_nextcloud") or "").strip() or None
        nombre_desde_enlace = _extraer_nombre_archivo_desde_enlace(enlace_nextcloud)
        extension_desde_enlace = _extension_desde_nombre_archivo(nombre_desde_enlace)
        if extension_desde_enlace:
            extension = _validar_extension(extension_desde_enlace)
        estado = (request.form.get("estado") or "VIGENTE").strip() or "VIGENTE"

        if not tipo:
            flash("Debes seleccionar el tipo de documento.", "danger")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id, tipo_documento=tipo_preseleccion or ""))

        # Validar que el tipo exista en el catálogo
        if tipo not in tipos_validos:
            flash("Tipo de documento inválido. Revisa el catálogo de tipos.", "danger")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id, tipo_documento=tipo_preseleccion or ""))

        try:
            doc = DocumentoLaboral.crear_para_contrato(
                contrato=contrato,
                tipo=tipo,
                fecha_ref=fecha_doc,
                extension=extension,
                ruta_archivo=enlace_nextcloud,
                estado=estado,
            )
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id, tipo_documento=tipo_preseleccion or ""))

        if nombre_desde_enlace:
            doc.nombre_archivo = nombre_desde_enlace

        db.session.add(doc)
        db.session.commit()

        if nombre_desde_enlace:
            flash(f"Documento registrado correctamente. Nombre detectado: {nombre_desde_enlace}", "success")
        else:
            flash("Documento registrado correctamente. No se pudo detectar el nombre real desde el enlace; puedes editarlo manualmente.", "warning")
        return redirect(next_url or url_for("documentos.documentos_por_contrato", contrato_id=contrato.id))

    return render_template(
        "documentos/nuevo_documento_contrato.html",
        contrato=contrato,
        documento_tipos=DOCUMENTO_TIPOS,
        tipo_preseleccion=tipo_preseleccion,
        next_url=next_url,
    )

@bp.route("/contrato/<int:contrato_id>/documento/<int:documento_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def editar_documento_contrato(contrato_id: int, documento_id: int):
    """Editar metadatos de un documento laboral ya registrado.

    Nota: esta edición no modifica el archivo físico en Nextcloud; solo actualiza
    la clasificación, estado, nombre lógico y enlace guardado en el expediente.
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    documento = DocumentoLaboral.query.filter_by(
        id=documento_id,
        contrato_id=contrato.id,
    ).first_or_404()

    if request.method == "POST":
        tipo = (request.form.get("tipo_documento") or "").strip()
        estado = (request.form.get("estado") or "VIGENTE").strip() or "VIGENTE"
        enlace_nextcloud = (request.form.get("enlace_nextcloud") or "").strip() or None
        nombre_archivo = (request.form.get("nombre_archivo") or "").strip()
        extension = _validar_extension(request.form.get("extension") or "pdf")
        fecha_doc_raw = request.form.get("fecha_documento")
        fecha_doc = parse_date(fecha_doc_raw) if fecha_doc_raw else None
        regenerar_nombre = request.form.get("regenerar_nombre") == "1"
        usar_nombre_desde_enlace = request.form.get("usar_nombre_desde_enlace") == "1"
        nombre_desde_enlace = _extraer_nombre_archivo_desde_enlace(enlace_nextcloud)
        extension_desde_enlace = _extension_desde_nombre_archivo(nombre_desde_enlace)
        if extension_desde_enlace:
            extension = _validar_extension(extension_desde_enlace)

        if not tipo:
            flash("Debes seleccionar el tipo de documento.", "danger")
            return redirect(url_for(
                "documentos.editar_documento_contrato",
                contrato_id=contrato.id,
                documento_id=documento.id,
            ))

        tipos_validos = {v for v, _label in DOCUMENTO_TIPOS}
        if tipo not in tipos_validos:
            flash("Tipo de documento inválido. Revisa el catálogo de tipos.", "danger")
            return redirect(url_for(
                "documentos.editar_documento_contrato",
                contrato_id=contrato.id,
                documento_id=documento.id,
            ))

        documento.tipo = tipo
        documento.estado = estado
        documento.ruta_archivo = enlace_nextcloud

        if usar_nombre_desde_enlace:
            if nombre_desde_enlace:
                documento.nombre_archivo = nombre_desde_enlace
            elif nombre_archivo:
                documento.nombre_archivo = nombre_archivo
                flash("No fue posible detectar el nombre desde el enlace. Se mantuvo el nombre indicado manualmente.", "warning")
        elif regenerar_nombre:
            try:
                doc_tmp = DocumentoLaboral.crear_para_contrato(
                    contrato=contrato,
                    tipo=tipo,
                    fecha_ref=fecha_doc,
                    extension=extension,
                    ruta_archivo=enlace_nextcloud,
                    estado=estado,
                )
                documento.nombre_archivo = doc_tmp.nombre_archivo
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for(
                    "documentos.editar_documento_contrato",
                    contrato_id=contrato.id,
                    documento_id=documento.id,
                ))
        elif nombre_archivo:
            documento.nombre_archivo = nombre_archivo

        db.session.commit()
        flash("Documento actualizado correctamente.", "success")
        return redirect(url_for("documentos.documentos_por_contrato", contrato_id=contrato.id))

    # Nombre real detectado desde el enlace actual.
    # Se calcula aquí para que exista tanto en GET como cuando un POST vuelve a renderizar el formulario.
    nombre_desde_enlace_actual = locals().get("nombre_desde_enlace_actual") or _extraer_nombre_archivo_desde_enlace(documento.ruta_archivo)

    return render_template(
        "documentos/editar_documento_contrato.html",
        contrato=contrato,
        documento=documento,
        documento_tipos=DOCUMENTO_TIPOS,
        nombre_desde_enlace=nombre_desde_enlace_actual if "nombre_desde_enlace_actual" in locals() else None,
    )


@bp.route("/contrato/<int:contrato_id>/documento/<int:documento_id>/eliminar", methods=["POST"])
@login_required
@role_required("ADMIN")
def eliminar_documento_contrato(contrato_id: int, documento_id: int):
    """Eliminar un registro documental del expediente del contrato.

    No borra archivos en Nextcloud; solo elimina el registro en el Sistema Grupo CS.
    """
    contrato = Contrato.query.get_or_404(contrato_id)
    documento = DocumentoLaboral.query.filter_by(
        id=documento_id,
        contrato_id=contrato.id,
    ).first_or_404()

    nombre = documento.nombre_archivo or "documento"
    db.session.delete(documento)
    db.session.commit()

    flash(f"Registro documental eliminado: {nombre}", "warning")
    return redirect(url_for("documentos.documentos_por_contrato", contrato_id=contrato.id))

