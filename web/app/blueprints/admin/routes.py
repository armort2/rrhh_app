# web/app/blueprints/admin/routes.py

import re
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from ...extensions import db
from ...models import User, Role, Obra
from ...services.system_health import build_system_health
from ...services.access_control import (
    ADMIN_PERMISSIONS,
    PERMISSION_GROUPS,
    PERMISSION_LABELS,
    get_blueprint_permission_rules,
    get_role_definitions,
)
from . import bp


_RUT_CLEAN_RE = re.compile(r"[^0-9kK]")


def _normalize_rut(value: str | None) -> str | None:
    """
    Normaliza RUT:
    - quita puntos/espacios
    - deja guion si viene; si no, intenta insertarlo
    - DV en mayúscula
    Retorna formato: 12345678-9 (sin puntos)
    No valida dígito verificador (se puede agregar después si quieres).
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    cleaned = _RUT_CLEAN_RE.sub("", raw).upper()
    if len(cleaned) < 2:
        return None

    cuerpo = cleaned[:-1]
    dv = cleaned[-1]
    if not cuerpo.isdigit():
        return None

    return f"{cuerpo}-{dv}"


def _require_admin():
    if not current_user.is_authenticated:
        abort(401)
    if not getattr(current_user, "has_role", None) or not current_user.has_role("ADMIN"):
        abort(403)


def _role_definitions_by_name():
    return {definition.name: definition for definition in get_role_definitions()}


@bp.get("/")
@login_required
def admin_home():
    _require_admin()
    return redirect(url_for("admin.users_list"))


@bp.get("/users/")
@login_required
def users_list():
    _require_admin()

    q = (request.args.get("q") or "").strip()

    query = User.query
    if q:
        q_norm = q.strip()

        # Si parece RUT, lo normalizamos para matchear mejor
        q_rut = _normalize_rut(q_norm) or q_norm

        query = query.filter(
            db.or_(
                User.username.ilike(f"%{q_norm}%"),
                User.email.ilike(f"%{q_norm}%"),
                User.nombre.ilike(f"%{q_norm}%"),
                User.rut.ilike(f"%{q_rut}%"),
            )
        )

    users = query.order_by(User.username.asc()).all()
    return render_template("admin/users_list.html", users=users, q=q)


@bp.get("/users/new")
@login_required
def users_new():
    _require_admin()

    roles = Role.query.order_by(Role.name.asc()).all()
    obras = Obra.query.order_by(Obra.nombre.asc()).all()

    return render_template(
        "admin/user_form.html",
        mode="new",
        user=None,
        roles=roles,
        obras=obras,
        selected_role_ids=[],
        selected_obra_ids=[],
        role_definitions_by_name=_role_definitions_by_name(),
    )


@bp.post("/users/new")
@login_required
def users_new_post():
    _require_admin()

    nombre = (request.form.get("nombre") or "").strip() or None
    rut = _normalize_rut(request.form.get("rut"))

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    password = request.form.get("password") or ""
    is_active = True if request.form.get("is_active") == "on" else False

    role_ids = request.form.getlist("roles")
    obra_ids = request.form.getlist("obras")

    if not username:
        flash("Debe ingresar un username.", "warning")
        return redirect(url_for("admin.users_new"))

    if User.query.filter_by(username=username).first():
        flash("Ya existe un usuario con ese username.", "danger")
        return redirect(url_for("admin.users_new"))

    if rut:
        # Evitar RUT duplicado (si lo usas como identificador)
        if User.query.filter_by(rut=rut).first():
            flash("Ya existe un usuario con ese RUT.", "danger")
            return redirect(url_for("admin.users_new"))

    if not password or len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("admin.users_new"))

    u = User(username=username, email=email, is_active=is_active)
    u.nombre = nombre
    u.rut = rut

    u.set_password(password)

    # Roles
    roles = Role.query.filter(Role.id.in_(role_ids)).all() if role_ids else []
    u.roles = roles

    # Obras
    obras = Obra.query.filter(Obra.id.in_(obra_ids)).all() if obra_ids else []
    u.obras = obras

    # Regla simple: si no es ADMIN, sugerimos asignar obra (no bloqueamos por ahora)
    if not u.has_role("ADMIN") and len(u.obras) == 0:
        flash("Usuario creado, pero sin obras asignadas. Sugerencia: asigna al menos 1 obra.", "warning")

    db.session.add(u)
    db.session.commit()

    flash("Usuario creado correctamente.", "info")
    return redirect(url_for("admin.users_list"))


@bp.get("/users/<int:user_id>/edit")
@login_required
def users_edit(user_id):
    _require_admin()

    u = User.query.get_or_404(user_id)
    roles = Role.query.order_by(Role.name.asc()).all()
    obras = Obra.query.order_by(Obra.nombre.asc()).all()

    selected_role_ids = [str(r.id) for r in u.roles]
    selected_obra_ids = [str(o.id) for o in u.obras]

    return render_template(
        "admin/user_form.html",
        mode="edit",
        user=u,
        roles=roles,
        obras=obras,
        selected_role_ids=selected_role_ids,
        selected_obra_ids=selected_obra_ids,
        role_definitions_by_name=_role_definitions_by_name(),
    )


@bp.post("/users/<int:user_id>/edit")
@login_required
def users_edit_post(user_id):
    _require_admin()

    u = User.query.get_or_404(user_id)

    nombre = (request.form.get("nombre") or "").strip() or None
    rut = _normalize_rut(request.form.get("rut"))

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    is_active = True if request.form.get("is_active") == "on" else False

    role_ids = request.form.getlist("roles")
    obra_ids = request.form.getlist("obras")

    if not username:
        flash("Debe ingresar un username.", "warning")
        return redirect(url_for("admin.users_edit", user_id=user_id))

    # evitar colisión de username
    other = User.query.filter_by(username=username).first()
    if other and other.id != u.id:
        flash("Ya existe otro usuario con ese username.", "danger")
        return redirect(url_for("admin.users_edit", user_id=user_id))

    # evitar colisión de RUT (si viene)
    if rut:
        other_rut = User.query.filter_by(rut=rut).first()
        if other_rut and other_rut.id != u.id:
            flash("Ya existe otro usuario con ese RUT.", "danger")
            return redirect(url_for("admin.users_edit", user_id=user_id))

    u.nombre = nombre
    u.rut = rut
    u.username = username
    u.email = email
    u.is_active = is_active

    # Roles y Obras
    u.roles = Role.query.filter(Role.id.in_(role_ids)).all() if role_ids else []
    u.obras = Obra.query.filter(Obra.id.in_(obra_ids)).all() if obra_ids else []

    db.session.commit()

    if not u.has_role("ADMIN") and len(u.obras) == 0:
        flash("Guardado OK. Nota: usuario no ADMIN sin obras asignadas.", "warning")
    else:
        flash("Usuario actualizado correctamente.", "info")

    return redirect(url_for("admin.users_list"))


@bp.post("/users/<int:user_id>/toggle-active")
@login_required
def users_toggle_active(user_id):
    _require_admin()

    u = User.query.get_or_404(user_id)

    # Evitar que el admin se dispare en el pie
    if u.id == current_user.id:
        flash("No puedes deshabilitar tu propio usuario.", "warning")
        return redirect(url_for("admin.users_list"))

    u.is_active = not u.is_active
    db.session.commit()

    flash("Estado de usuario actualizado.", "info")
    return redirect(url_for("admin.users_list"))


@bp.post("/users/<int:user_id>/reset-password")
@login_required
def users_reset_password(user_id):
    _require_admin()

    u = User.query.get_or_404(user_id)
    new_password = request.form.get("new_password") or ""

    if not new_password or len(new_password) < 8:
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "warning")
        return redirect(url_for("admin.users_edit", user_id=user_id))

    u.set_password(new_password)
    u.must_change_password = True
    db.session.commit()

    flash("Contraseña restablecida. Se marcó 'must_change_password'.", "info")
    return redirect(url_for("admin.users_edit", user_id=user_id))




@bp.get("/roles-matriz")
@login_required
def roles_matriz():
    _require_admin()

    role_definitions = get_role_definitions()
    permission_groups = PERMISSION_GROUPS
    permission_labels = PERMISSION_LABELS
    blueprint_rules = get_blueprint_permission_rules()
    total_roles = len(role_definitions)
    total_permissions = len(ADMIN_PERMISSIONS)
    total_blueprint_rules = len(blueprint_rules)

    return render_template(
        "admin/roles_matriz.html",
        role_definitions=role_definitions,
        permission_groups=permission_groups,
        permission_labels=permission_labels,
        blueprint_rules=blueprint_rules,
        total_roles=total_roles,
        total_permissions=total_permissions,
        total_blueprint_rules=total_blueprint_rules,
    )


@bp.get("/salud-sistema")
@login_required
def salud_sistema():
    _require_admin()
    health = build_system_health()
    return render_template("admin/salud_sistema.html", health=health)


def _parse_date_yyyy_mm_dd(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except Exception:
        return None


@bp.get("/auditoria")
@login_required
def auditoria():
    _require_admin()

    from datetime import timedelta
    from sqlalchemy import func
    from ...models import AuditLog

    page = max(int(request.args.get("page") or 1), 1)
    per_page = 100

    user_id = (request.args.get("user_id") or "").strip()
    section = (request.args.get("section") or "").strip()
    event_type = (request.args.get("event_type") or "").strip()
    method = (request.args.get("method") or "").strip().upper()
    q = (request.args.get("q") or "").strip()
    desde = (request.args.get("desde") or "").strip()
    hasta = (request.args.get("hasta") or "").strip()

    query = AuditLog.query

    if user_id.isdigit():
        query = query.filter(AuditLog.user_id == int(user_id))
    if section:
        query = query.filter(AuditLog.section == section)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    if method:
        query = query.filter(AuditLog.method == method)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                AuditLog.username.ilike(like),
                AuditLog.nombre.ilike(like),
                AuditLog.path.ilike(like),
                AuditLog.endpoint.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.ip_address.ilike(like),
            )
        )

    desde_dt = _parse_date_yyyy_mm_dd(desde)
    hasta_dt = _parse_date_yyyy_mm_dd(hasta)
    if desde_dt:
        query = query.filter(AuditLog.created_at >= desde_dt)
    if hasta_dt:
        query = query.filter(AuditLog.created_at < hasta_dt + timedelta(days=1))

    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    base_for_stats = query.subquery()
    total = db.session.query(func.count()).select_from(base_for_stats).scalar() or 0

    usuarios_activos = (
        db.session.query(AuditLog.username, AuditLog.nombre, func.count(AuditLog.id).label("total"))
        .filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=7))
        .group_by(AuditLog.username, AuditLog.nombre)
        .order_by(func.count(AuditLog.id).desc())
        .limit(8)
        .all()
    )

    secciones_top = (
        db.session.query(AuditLog.section, func.count(AuditLog.id).label("total"))
        .filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=7))
        .group_by(AuditLog.section)
        .order_by(func.count(AuditLog.id).desc())
        .limit(8)
        .all()
    )

    negocios_ultimos_7 = (
        db.session.query(func.count(AuditLog.id))
        .filter(AuditLog.event_type == "business")
        .filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=7))
        .scalar()
        or 0
    )

    negocios_top = (
        db.session.query(AuditLog.section, AuditLog.action, func.count(AuditLog.id).label("total"))
        .filter(AuditLog.event_type == "business")
        .filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=30))
        .group_by(AuditLog.section, AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(8)
        .all()
    )

    sections = [
        row[0]
        for row in db.session.query(AuditLog.section)
        .filter(AuditLog.section.isnot(None))
        .distinct()
        .order_by(AuditLog.section.asc())
        .all()
    ]
    users = User.query.order_by(User.username.asc()).all()

    filtros = {
        "user_id": user_id,
        "section": section,
        "event_type": event_type,
        "method": method,
        "q": q,
        "desde": desde,
        "hasta": hasta,
    }

    return render_template(
        "admin/auditoria.html",
        logs=pagination.items,
        pagination=pagination,
        filtros=filtros,
        users=users,
        sections=sections,
        total=total,
        usuarios_activos=usuarios_activos,
        secciones_top=secciones_top,
        negocios_ultimos_7=negocios_ultimos_7,
        negocios_top=negocios_top,
    )
