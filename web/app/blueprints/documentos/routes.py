from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
)

from ... import db
from ...models import Contrato, DocumentoLaboral
from ...config import DOCUMENTO_TIPOS


bp = Blueprint("documentos", __name__, url_prefix="/documentos")


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/contrato/<int:contrato_id>")
def documentos_por_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)

    # Mapeo value -> label para mostrar el nombre bonito del tipo
    tipos_dict = dict(DOCUMENTO_TIPOS)

    return render_template(
        "documentos/documentos_por_contrato.html",
        contrato=contrato,
        tipos_dict=tipos_dict,
    )


@bp.route("/contrato/<int:contrato_id>/nuevo", methods=["GET", "POST"])
def nuevo_documento_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)

    if request.method == "POST":
        tipo = request.form.get("tipo_documento")
        fecha_doc = _parse_date(request.form.get("fecha_documento"))
        extension = request.form.get("extension") or "pdf"
        enlace_nextcloud = request.form.get("enlace_nextcloud") or None
        estado = request.form.get("estado") or "VIGENTE"

        if not tipo:
            flash("Debes seleccionar el tipo de documento.", "error")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id))

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
            flash(str(e), "error")
            return redirect(url_for("documentos.nuevo_documento_contrato", contrato_id=contrato.id))

        db.session.add(doc)
        db.session.commit()

        flash("Documento registrado correctamente.", "success")
        return redirect(url_for("documentos.documentos_por_contrato", contrato_id=contrato.id))

    return render_template(
        "documentos/nuevo_documento_contrato.html",
        contrato=contrato,
        documento_tipos=DOCUMENTO_TIPOS,
    )
