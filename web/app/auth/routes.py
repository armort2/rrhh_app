# web/app/auth/routes.py
from datetime import datetime
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from . import auth


def _is_safe_next_url(target: str) -> bool:
    """
    Permite redirecciones solo internas (mismo host / rutas relativas).
    Evita open redirect.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    if test_url.scheme and test_url.netloc:
        # Si viene absoluto, debe ser mismo host
        return (test_url.scheme, test_url.netloc) == (ref_url.scheme, ref_url.netloc)
    # Si es relativo, es seguro
    return target.startswith("/")


@auth.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("core.index"))
    return render_template("auth/login.html")


@auth.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        flash("Usuario o contraseña inválidos.", "danger")
        return redirect(url_for("auth.login", next=request.args.get("next")))

    if not user.is_active:
        flash("Usuario deshabilitado. Contacte al administrador.", "warning")
        return redirect(url_for("auth.login", next=request.args.get("next")))

    login_user(user, remember=True)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    next_url = request.args.get("next")
    if next_url and _is_safe_next_url(next_url):
        return redirect(next_url)

    return redirect(url_for("core.index"))


@auth.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
