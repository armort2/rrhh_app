# web/app/services/access_control.py
"""
Control de acceso institucional del Sistema Grupo CS.

V9 fortalece la matriz de roles/permisos con una capa central de protección
por blueprint. La regla es conservadora: primero se protegen módulos completos
por permisos de lectura/escritura, sin crear migraciones ni cambiar tablas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    label: str
    description: str
    permissions: tuple[str, ...]
    legacy_equivalent: str | None = None


@dataclass(frozen=True)
class BlueprintPermissionRule:
    blueprint: str
    label: str
    read_permission: str
    write_permission: str | None = None
    notes: str = ""


ALL_PERMISSION = "*"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints GET que abren formularios o procesos de emisión/generación.
# Aunque sean GET, funcionalmente son de operación; por eso se exige permiso
# de escritura cuando el endpoint contiene alguno de estos términos.
WRITE_ENDPOINT_KEYWORDS = (
    "nuevo",
    "nueva",
    "crear",
    "editar",
    "eliminar",
    "borrar",
    "delete",
    "toggle",
    "activar",
    "desactivar",
    "importar",
    "generar",
    "emitir",
    "guardar",
    "aprobar",
    "rechazar",
    "anular",
    "preparar",
    "sincronizar",
    "sync",
    "descargar",
    "exportar",
    "recalcular",
    "restablecer",
    "reset",
)


ROLE_DEFINITIONS: dict[str, RoleDefinition] = {
    "ADMIN": RoleDefinition(
        name="ADMIN",
        label="Administrador total",
        description="Acceso completo al sistema, usuarios, parámetros, auditoría y mantención técnica.",
        permissions=(ALL_PERMISSION,),
        legacy_equivalent="ADMIN",
    ),
    "FINANZAS": RoleDefinition(
        name="FINANZAS",
        label="Finanzas",
        description="Opera módulos financieros: flujo, pagos, nóminas, anticipos, sueldos y extras. Lectura de RRHH.",
        permissions=(
            "personas.ver",
            "documentos.ver",
            "operacion.ver",
            "operacion.finanzas",
            "flujo.ver",
            "flujo.editar",
            "flujo.solicitudes.ver",
            "flujo.solicitudes.editar",
            "flujo.rendiciones.ver",
            "flujo.rendiciones.crear",
            "flujo.pagos.ver",
            "flujo.pagos.editar",
            "dashboard.ver",
            "dashboard.solicitudes_fondos.ver",
            "reporteria.ver",
        ),
    ),
    "ADMINISTRATIVO": RoleDefinition(
        name="ADMINISTRATIVO",
        label="Administrativo RRHH",
        description="Opera RRHH: trabajadores, contratos, anexos, desvinculaciones, certificados, egresos y acuerdos. Sin solicitudes de fondos.",
        permissions=(
            "personas.ver",
            "personas.editar",
            "documentos.ver",
            "documentos.editar",
            "operacion.ver",
            "operacion.rrhh",
            "flujo.ver",
            "flujo.rendiciones.ver",
            "flujo.rendiciones.crear",
            "flujo.egresos.ver",
            "flujo.egresos.editar",
            "dashboard.ver",
            "reporteria.ver",
        ),
        legacy_equivalent="OPERADOR",
    ),
    "JEFATURA": RoleDefinition(
        name="JEFATURA",
        label="Jefatura",
        description="Opera Flujo con libertad y revisa el resto del sistema sin funciones administrativas críticas.",
        permissions=(
            "personas.ver",
            "documentos.ver",
            "operacion.ver",
            "operacion.revisar",
            "prevencion.ver",
            "flujo.ver",
            "flujo.editar",
            "flujo.solicitudes.ver",
            "flujo.solicitudes.editar",
            "flujo.rendiciones.ver",
            "flujo.rendiciones.crear",
            "flujo.pagos.ver",
            "dashboard.ver",
            "dashboard.solicitudes_fondos.ver",
            "reporteria.ver",
        ),
    ),
    "PREVENCION": RoleDefinition(
        name="PREVENCION",
        label="Prevención de Riesgos",
        description="Opera prevención y revisa datos necesarios de trabajadores, contratos, obras y reportes preventivos.",
        permissions=(
            "personas.ver",
            "documentos.ver",
            "prevencion.ver",
            "prevencion.editar",
            "dashboard.ver",
            "reporteria.ver",
        ),
    ),
    "SOLO_LECTURA": RoleDefinition(
        name="SOLO_LECTURA",
        label="Solo lectura",
        description="Consulta información autorizada sin crear, modificar, emitir ni eliminar registros.",
        permissions=(
            "personas.ver",
            "documentos.ver",
            "operacion.ver",
            "prevencion.ver",
            "flujo.rendiciones.ver",
            "dashboard.ver",
            "reporteria.ver",
        ),
        legacy_equivalent="REVISOR",
    ),
    "RENDIDOR": RoleDefinition(
        name="RENDIDOR",
        label="Rendidor",
        description="Crea rendiciones de gastos y revisa sus rendiciones asociadas. Rol combinable con otros perfiles.",
        permissions=(
            "flujo.ver",
            "flujo.rendiciones.ver",
            "flujo.rendiciones.crear",
        ),
    ),
    # Roles históricos conservados para compatibilidad con rutas existentes.
    "OPERADOR": RoleDefinition(
        name="OPERADOR",
        label="Operador histórico",
        description="Rol heredado. Se mantiene por compatibilidad; migrar gradualmente a ADMINISTRATIVO / FINANZAS / JEFATURA.",
        permissions=(
            "personas.ver",
            "personas.editar",
            "documentos.ver",
            "documentos.editar",
            "operacion.ver",
            "operacion.rrhh",
            "operacion.finanzas",
            "prevencion.ver",
            "prevencion.editar",
            "flujo.ver",
            "flujo.editar",
            "flujo.solicitudes.ver",
            "flujo.solicitudes.editar",
            "flujo.rendiciones.ver",
            "flujo.rendiciones.crear",
            "flujo.pagos.ver",
            "flujo.pagos.editar",
            "flujo.egresos.ver",
            "flujo.egresos.editar",
            "dashboard.ver",
            "dashboard.solicitudes_fondos.ver",
            "reporteria.ver",
        ),
        legacy_equivalent="OPERADOR",
    ),
    "REVISOR": RoleDefinition(
        name="REVISOR",
        label="Revisor histórico",
        description="Rol heredado de lectura. Se mantiene por compatibilidad; migrar gradualmente a SOLO_LECTURA.",
        permissions=(
            "personas.ver",
            "documentos.ver",
            "operacion.ver",
            "prevencion.ver",
            "flujo.ver",
            "flujo.rendiciones.ver",
            "dashboard.ver",
            "reporteria.ver",
        ),
        legacy_equivalent="REVISOR",
    ),
}

ROLE_ORDER: tuple[str, ...] = (
    "ADMIN",
    "FINANZAS",
    "ADMINISTRATIVO",
    "JEFATURA",
    "PREVENCION",
    "SOLO_LECTURA",
    "RENDIDOR",
    "OPERADOR",
    "REVISOR",
)

PERMISSION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Personas", ("personas.ver", "personas.editar")),
    ("Documentos RRHH", ("documentos.ver", "documentos.editar")),
    ("Operación", ("operacion.ver", "operacion.rrhh", "operacion.finanzas", "operacion.revisar")),
    ("Prevención", ("prevencion.ver", "prevencion.editar")),
    ("Flujo", ("flujo.ver", "flujo.editar", "flujo.solicitudes.ver", "flujo.solicitudes.editar", "flujo.rendiciones.ver", "flujo.rendiciones.crear", "flujo.pagos.ver", "flujo.pagos.editar", "flujo.egresos.ver", "flujo.egresos.editar")),
    ("Dashboard / Reportería", ("dashboard.ver", "dashboard.solicitudes_fondos.ver", "reporteria.ver")),
    ("Administración", ("admin.panel", "admin.usuarios", "admin.auditoria", "admin.salud", "admin.parametros")),
)

PERMISSION_LABELS: dict[str, str] = {
    "personas.ver": "Ver personas/obras/terceros",
    "personas.editar": "Crear/editar personas",
    "documentos.ver": "Ver documentos RRHH",
    "documentos.editar": "Crear/emitir documentos RRHH",
    "operacion.ver": "Ver operación",
    "operacion.rrhh": "Operar inasistencias/horas extra",
    "operacion.finanzas": "Operar anticipos/sueldos/extras",
    "operacion.revisar": "Revisar operación",
    "prevencion.ver": "Ver prevención",
    "prevencion.editar": "Operar prevención",
    "flujo.ver": "Ver menú Flujo",
    "flujo.editar": "Operar Flujo general",
    "flujo.solicitudes.ver": "Ver solicitudes de fondos",
    "flujo.solicitudes.editar": "Crear/editar solicitudes de fondos",
    "flujo.rendiciones.ver": "Ver rendiciones",
    "flujo.rendiciones.crear": "Crear rendiciones",
    "flujo.pagos.ver": "Ver pagos/transferencias/proveedores",
    "flujo.pagos.editar": "Operar pagos/transferencias/proveedores",
    "flujo.egresos.ver": "Ver egresos/acuerdos",
    "flujo.egresos.editar": "Operar egresos/acuerdos",
    "dashboard.ver": "Ver dashboard",
    "dashboard.solicitudes_fondos.ver": "Ver dashboard solicitudes de fondos",
    "reporteria.ver": "Ver reportería",
    "admin.panel": "Ver Admin",
    "admin.usuarios": "Administrar usuarios",
    "admin.auditoria": "Ver auditoría",
    "admin.salud": "Ver salud del sistema",
    "admin.parametros": "Administrar parámetros",
}

# Protección V9 por módulos. Se aplica en before_request, luego del login global.
# La protección profunda de acciones específicas queda para una etapa posterior,
# pero esta barrera ya impide acceder por URL directa a módulos no autorizados.
BLUEPRINT_PERMISSION_RULES: dict[str, BlueprintPermissionRule] = {
    "trabajadores": BlueprintPermissionRule("trabajadores", "Trabajadores", "personas.ver", "personas.editar"),
    "obras": BlueprintPermissionRule("obras", "Obras", "personas.ver", "personas.editar"),
    "terceros": BlueprintPermissionRule("terceros", "Terceros", "personas.ver", "personas.editar"),
    "contratos": BlueprintPermissionRule("contratos", "Contratos", "documentos.ver", "documentos.editar"),
    "contratos_vencimientos": BlueprintPermissionRule("contratos_vencimientos", "Contratos por vencer", "documentos.ver", None),
    "anexos": BlueprintPermissionRule("anexos", "Anexos plazo fijo", "documentos.ver", "documentos.editar"),
    "anexos_indefinidos": BlueprintPermissionRule("anexos_indefinidos", "Anexos indefinidos", "documentos.ver", "documentos.editar"),
    "anexos_cambio_sueldo": BlueprintPermissionRule("anexos_cambio_sueldo", "Anexos cambio sueldo", "documentos.ver", "documentos.editar"),
    "anexos_cambio_cargo": BlueprintPermissionRule("anexos_cambio_cargo", "Anexos cambio cargo", "documentos.ver", "documentos.editar"),
    "anexos_masivos": BlueprintPermissionRule("anexos_masivos", "Anexos masivos", "documentos.ver", "documentos.editar"),
    "desvinculaciones": BlueprintPermissionRule("desvinculaciones", "Desvinculaciones", "documentos.ver", "documentos.editar"),
    "documentos": BlueprintPermissionRule("documentos", "Documentos", "documentos.ver", "documentos.editar"),
    "certificados": BlueprintPermissionRule("certificados", "Certificados", "documentos.ver", "documentos.editar"),
    "vacaciones": BlueprintPermissionRule("vacaciones", "Vacaciones", "documentos.ver", "documentos.editar"),
    "inasistencias": BlueprintPermissionRule("inasistencias", "Inasistencias", "operacion.ver", "operacion.rrhh"),
    "horas_extras": BlueprintPermissionRule("horas_extras", "Horas extras", "operacion.ver", "operacion.rrhh"),
    "anticipos": BlueprintPermissionRule("anticipos", "Anticipos", "operacion.ver", "operacion.finanzas"),
    "sueldos": BlueprintPermissionRule("sueldos", "Sueldos", "operacion.ver", "operacion.finanzas"),
    "extras_remuneracion": BlueprintPermissionRule("extras_remuneracion", "Bonos, tratos y extras", "operacion.ver", "operacion.finanzas"),
    "prevencion_riesgos": BlueprintPermissionRule("prevencion_riesgos", "Prevención de Riesgos", "prevencion.ver", "prevencion.editar"),
    "solicitudes_fondos": BlueprintPermissionRule("solicitudes_fondos", "Solicitudes de fondos", "flujo.solicitudes.ver", "flujo.solicitudes.editar"),
    "rendiciones_gastos": BlueprintPermissionRule("rendiciones_gastos", "Rendiciones de gastos", "flujo.rendiciones.ver", "flujo.rendiciones.crear"),
    "pago_proveedores": BlueprintPermissionRule("pago_proveedores", "Pago proveedores", "flujo.pagos.ver", "flujo.pagos.editar"),
    "transferencias_bancarias": BlueprintPermissionRule("transferencias_bancarias", "Transferencias bancarias", "flujo.pagos.ver", "flujo.pagos.editar"),
    "egresos": BlueprintPermissionRule("egresos", "Egresos", "flujo.egresos.ver", "flujo.egresos.editar"),
    "acuerdos_pago": BlueprintPermissionRule("acuerdos_pago", "Acuerdos de pago", "flujo.egresos.ver", "flujo.egresos.editar"),
    "dashboard": BlueprintPermissionRule("dashboard", "Dashboard", "dashboard.ver", None),
    "reporteria": BlueprintPermissionRule("reporteria", "Reportería", "reporteria.ver", None),
    "cumplimiento_laboral": BlueprintPermissionRule("cumplimiento_laboral", "Cumplimiento Laboral", "reporteria.ver", None),
    "gestion_rrhh": BlueprintPermissionRule("gestion_rrhh", "Bandeja de Gestión RRHH", "dashboard.ver", None),
    "horarios": BlueprintPermissionRule("horarios", "Horarios", "admin.parametros", "admin.parametros"),
    "feriados": BlueprintPermissionRule("feriados", "Feriados", "admin.parametros", "admin.parametros"),
    "parametros_laborales": BlueprintPermissionRule("parametros_laborales", "Parámetros laborales", "admin.parametros", "admin.parametros"),
}

ADMIN_PERMISSIONS = tuple(
    permission
    for _, permissions in PERMISSION_GROUPS
    for permission in permissions
)


def normalize_role_name(value: str | None) -> str:
    return (value or "").strip().upper()


def get_role_definitions() -> list[RoleDefinition]:
    return [ROLE_DEFINITIONS[name] for name in ROLE_ORDER if name in ROLE_DEFINITIONS]


def get_role_definition(name: str | None) -> RoleDefinition | None:
    return ROLE_DEFINITIONS.get(normalize_role_name(name))


def get_blueprint_permission_rules() -> list[BlueprintPermissionRule]:
    return sorted(BLUEPRINT_PERMISSION_RULES.values(), key=lambda rule: rule.label.lower())


def roles_for_user(user) -> set[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    roles = getattr(user, "roles", None) or []
    return {normalize_role_name(getattr(role, "name", None)) for role in roles if getattr(role, "name", None)}


def permissions_for_roles(role_names: Iterable[str]) -> set[str]:
    normalized = {normalize_role_name(role) for role in role_names}
    if "ADMIN" in normalized:
        return {ALL_PERMISSION, *ADMIN_PERMISSIONS}

    permissions: set[str] = set()
    for role_name in normalized:
        definition = ROLE_DEFINITIONS.get(role_name)
        if definition:
            permissions.update(definition.permissions)
    return permissions


def user_permissions(user) -> set[str]:
    return permissions_for_roles(roles_for_user(user))


def user_can(user, permission: str) -> bool:
    permission = (permission or "").strip()
    if not permission:
        return False
    permissions = user_permissions(user)
    return ALL_PERMISSION in permissions or permission in permissions


def user_has_any_permission(user, *permissions: str) -> bool:
    return any(user_can(user, permission) for permission in permissions)


def user_has_role(user, *roles: str) -> bool:
    user_roles = roles_for_user(user)
    wanted = {normalize_role_name(role) for role in roles}
    return bool(user_roles.intersection(wanted))


def endpoint_is_write_like(endpoint: str | None) -> bool:
    action = (endpoint or "").split(".", 1)[-1].lower()
    return any(keyword in action for keyword in WRITE_ENDPOINT_KEYWORDS)


def required_permission_for_request(
    blueprint: str | None,
    endpoint: str | None,
    method: str | None,
) -> str | None:
    """Devuelve el permiso requerido para el request actual.

    - None significa que esta capa V9 no controla ese endpoint.
    - Los métodos de escritura siempre piden permiso de escritura si existe.
    - Algunos endpoints GET con nombre operativo también piden permiso de escritura.
    """
    bp = (blueprint or "").strip()
    if not bp or bp in {"auth", "static"}:
        return None

    # El home y ping quedan fuera de la barrera RBAC para no romper entrada/salud.
    if bp == "core":
        action = (endpoint or "").split(".", 1)[-1]
        if action in {"index", "ping"}:
            return None
        # En core, actualmente el caso relevante es cargos, ya protegido por ADMIN.
        if action.startswith("cargo") or action.startswith("cargos"):
            return "admin.parametros"
        return None

    # Admin conserva además sus validaciones internas; esta capa solo da coherencia.
    if bp == "admin":
        action = (endpoint or "").split(".", 1)[-1]
        if action in {"auditoria"}:
            return "admin.auditoria"
        if action in {"salud_sistema"}:
            return "admin.salud"
        if action in {"roles_matriz", "users_list", "users_new", "users_edit", "users_reset_password"}:
            return "admin.usuarios"
        return "admin.panel"

    if bp == "dashboard":
        action = (endpoint or "").split(".", 1)[-1]
        if action == "solicitudes_fondos":
            return "dashboard.solicitudes_fondos.ver"

    rule = BLUEPRINT_PERMISSION_RULES.get(bp)
    if not rule:
        return None

    method_norm = (method or "GET").upper()
    if method_norm in WRITE_METHODS or endpoint_is_write_like(endpoint):
        return rule.write_permission or rule.read_permission
    return rule.read_permission


def user_can_access_request(user, blueprint: str | None, endpoint: str | None, method: str | None) -> bool:
    required = required_permission_for_request(blueprint, endpoint, method)
    if required is None:
        return True
    return user_can(user, required)
