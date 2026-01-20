# web/app/auth/decorators.py

from __future__ import annotations

from functools import wraps

from flask import abort, request
from flask_login import login_required, current_user


def _normalize_roles(*roles: str) -> tuple[str, ...]:
    return tuple(r.strip().upper() for r in roles if (r or "").strip())


def active_user_required(abort_code: int = 403):
    """
    Restringe acceso solo a usuarios activos.
    - Si el usuario NO está activo => abort(abort_code)
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_active", False):
                abort(abort_code)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def role_required(*roles: str, abort_code: int = 403):
    """
    Restringe acceso por rol (OR).
    Uso: @role_required("ADMIN", "OPERADOR")

    - Si el usuario NO está activo => abort(abort_code)
    - Si NO tiene al menos uno de los roles requeridos => abort(abort_code)
    - Si por error se llama sin roles => abort(abort_code) (fail-closed)
    """
    roles_norm = _normalize_roles(*roles)

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_active", False):
                abort(abort_code)

            # Fail-closed: si no se especifican roles, se bloquea.
            if not roles_norm:
                abort(abort_code)

            # OR explícito: basta con que tenga UNO de los roles.
            if not any(current_user.has_role(r) for r in roles_norm):
                abort(abort_code)

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# Alias semántico (por si prefieres plural)
def roles_required(*roles: str, abort_code: int = 403):
    return role_required(*roles, abort_code=abort_code)


def read_only_for_roles(*roles: str, abort_code: int = 403):
    """
    Convierte un endpoint en "solo lectura" para ciertos roles.
    - Si el request method es de escritura (POST/PUT/PATCH/DELETE)
      y el usuario tiene alguno de esos roles => abort(abort_code)

    Uso típico:
      @bp.route("/obras/<int:id>/editar", methods=["GET","POST"])
      @login_required
      @read_only_for_roles("OPERADOR", "REVISOR")
      def editar(...):
          ...

    Nota: si además usas @role_required("ADMIN") en el mismo endpoint,
    este decorador es redundante; sirve cuando quieres permitir GET
    a roles no-admin, pero bloquear escritura.
    """
    roles_norm = _normalize_roles(*roles)
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_active", False):
                abort(abort_code)

            # Si no se especifican roles, no aplica bloqueo (no fail-closed aquí),
            # porque su propósito es "bloquear a X", no "autorizar a X".
            if roles_norm and request.method in write_methods:
                if any(current_user.has_role(r) for r in roles_norm):
                    abort(abort_code)

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def obra_required(param_name: str = "obra_id", abort_code: int = 403):
    """
    Restringe acceso por obra.
    - ADMIN: acceso total
    - Otros: solo si obra_id está asignada al usuario

    Espera obra_id en kwargs (por ejemplo /obras/<int:obra_id>/...)
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_active", False):
                abort(abort_code)

            obra_id = kwargs.get(param_name)
            if obra_id is None:
                abort(400)

            if current_user.has_role("ADMIN"):
                return fn(*args, **kwargs)

            if not current_user.can_access_obra(int(obra_id)):
                abort(abort_code)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
