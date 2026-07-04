from __future__ import annotations

from flask import render_template
from flask_login import current_user, login_required

from ...auth.decorators import role_required
from ...services.cumplimiento_laboral import construir_panel_cumplimiento
from . import bp


ROLES_CUMPLIMIENTO_VER = (
    "ADMIN",
    "ADMINISTRATIVO",
    "JEFATURA",
    "PREVENCION",
    "SOLO_LECTURA",
    "OPERADOR",
    "REVISOR",
)


@bp.get("/")
@login_required
@role_required(*ROLES_CUMPLIMIENTO_VER)
def index():
    panel = construir_panel_cumplimiento(current_user)
    return render_template("cumplimiento_laboral/index.html", panel=panel)


@bp.get("/ley-karin")
@login_required
@role_required(*ROLES_CUMPLIMIENTO_VER)
def ley_karin():
    panel = construir_panel_cumplimiento(current_user)
    return render_template("cumplimiento_laboral/ley_karin.html", panel=panel)
