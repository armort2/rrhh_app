# web/app/auth/routes.py
from datetime import datetime
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from ..common.navigation import is_safe_redirect_target
from ..services.audit import audit_event
from . import auth



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
    audit_event("login", "Inicio de sesión correcto", user=user)

    next_url = request.args.get("next")
    if next_url and is_safe_redirect_target(next_url):
        return redirect(next_url)

    return redirect(url_for("core.index"))


@auth.get("/logout")
@login_required
def logout():
    audit_event("logout", "Cierre de sesión", user=current_user)
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
