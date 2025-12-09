# web/app/blueprints/obras/routes.py

from flask import render_template, request, redirect, url_for, flash

from ...extensions import db
from ...models import Obra

from . import bp


@bp.route("/")
def lista_obras():
    obras = Obra.query.order_by(Obra.nombre).all()
    return render_template("obras.html", obras=obras)


@bp.route("/nueva", methods=["GET", "POST"])
def nueva_obra():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        codigo = request.form.get("codigo")
        centro_costo = request.form.get("centro_costo")
        comuna = request.form.get("comuna")
        estado = request.form.get("estado") or "ACTIVA"

        if not (nombre and codigo):
            flash("Nombre y código de la obra son obligatorios.")
            return redirect(url_for("obras.nueva_obra"))

        o = Obra(
            nombre=nombre,
            codigo=codigo,
            centro_costo=centro_costo,
            comuna=comuna,
            estado=estado,
        )
        db.session.add(o)
        db.session.commit()

        flash("Obra creada correctamente.")
        return redirect(url_for("obras.lista_obras"))

    return render_template("nueva_obra.html")
