from flask import (
    render_template,
    redirect,
    url_for,
    request,
    flash,
)
from flask_login import login_required

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


@bp.route("/contrato/<int:contrato_id>")
@login_required
@role_required("ADMIN")
def documentos_por_contrato(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)

    # Mapeo value -> label para mostrar el nombre bonito del tipo
    tipos_dict = dict(DOCUMENTO_TIPOS)

    return render_template(
        "documentos/documentos_por_contrato.html",
        contrato=contrato,
        tipos_dict=tipos_dict,
    )


@bp.route("/contrato/<int:contrato_id>/nuevo", methods=["GET", "POST"])
@login_required
@role_required("ADMIN")
def nuevo_documento_contrato(contrato_id: int):
    contrato = Contrato.query.get_or_404(contrato_id)

    # Permite preselección desde el botón del detalle:
    # /documentos/contrato/<id>/nuevo?tipo_documento=CONTRATO
    tipo_preseleccion = (request.args.get("tipo_documento") or "").strip() or None

    if request.method == "POST":
        tipo = (request.form.get("tipo_documento") or "").strip()
        fecha_doc_raw = request.form.get("fecha_documento")  # puede venir vacío
        fecha_doc = parse_date(fecha_doc_raw) if fecha_doc_raw else None

        extension = _validar_extension(request.form.get("extension") or "pdf")
        enlace_nextcloud = (request.form.get("enlace_nextcloud") or "").strip() or None
        estado = (request.form.get("estado") or "VIGENTE").strip() or "VIGENTE"

        if not tipo:
            flash("Debes seleccionar el tipo de documento.", "danger")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id, tipo_documento=tipo_preseleccion or ""))

        # Validar que el tipo exista en el catálogo
        tipos_validos = {v for v, _label in DOCUMENTO_TIPOS}
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

        db.session.add(doc)
        db.session.commit()

        flash("Documento registrado correctamente.", "success")
        return redirect(url_for("documentos.documentos_por_contrato", contrato_id=contrato.id))

    return render_template(
        "documentos/nuevo_documento_contrato.html",
        contrato=contrato,
        documento_tipos=DOCUMENTO_TIPOS,
        tipo_preseleccion=tipo_preseleccion,
    )
