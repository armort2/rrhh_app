# web/app/auth/decorators.py
from functools import wraps

from flask import abort
from flask_login import login_required, current_user


def role_required(*roles: str):
    """
    Restringe acceso por rol (OR).
    Uso: @role_required("ADMIN", "OPERADOR")

    - Si el usuario NO está activo => 403
    - Si NO tiene al menos uno de los roles requeridos => 403
    """
    roles = tuple(r.strip().upper() for r in roles if (r or "").strip())

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_active", False):
                abort(403)

            # Si por error se llama sin roles, bloqueamos (fail-closed).
            if not roles:
                abort(403)

            # OR explícito: basta con que tenga UNO de los roles.
            if not any(current_user.has_role(r) for r in roles):
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def obra_required(param_name: str = "obra_id"):
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
            obra_id = kwargs.get(param_name)
            if obra_id is None:
                abort(400)

            if current_user.has_role("ADMIN"):
                return fn(*args, **kwargs)

            if not current_user.can_access_obra(int(obra_id)):
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
