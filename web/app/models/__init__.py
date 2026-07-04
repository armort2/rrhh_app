# web/app/models/__init__.py
"""
Paquete app.models

Puente mientras migramos desde models_legacy.py hacia módulos en app/models/*.py

Objetivo:
- Exponer *todos* los modelos legacy vía `from app.models import X`
  (sin depender de __all__ del legacy)
- Exponer modelos nuevos modulares
"""

from __future__ import annotations

# ------------------------------------------------------------
# 1) Cargar legacy como módulo (NO import *)
# ------------------------------------------------------------
from .. import models_legacy as _legacy  # type: ignore

for _name, _obj in _legacy.__dict__.items():
    if _name.startswith("_"):
        continue
    globals()[_name] = _obj

# ------------------------------------------------------------
# 2) Modelos nuevos modulares
# ------------------------------------------------------------

# Pago a Proveedores
from .pago_proveedores import PagoProveedoresLote, PagoProveedoresItem  # noqa: F401
globals()["PagoProveedoresLote"] = PagoProveedoresLote
globals()["PagoProveedoresItem"] = PagoProveedoresItem

# Extras Remuneración (modelo real en singular)
from .extras_remu import ExtraRemuLote, ExtraRemuItem  # noqa: F401
globals()["ExtraRemuLote"] = ExtraRemuLote
globals()["ExtraRemuItem"] = ExtraRemuItem

# Backward-compat alias (el blueprint usa plural)
globals()["ExtrasRemuLote"] = ExtraRemuLote
globals()["ExtrasRemuItem"] = ExtraRemuItem

# Contratos Vencimientos
from .contratos_vencimientos import ContratoVencimientoDecision  # noqa: F401
globals()["ContratoVencimientoDecision"] = ContratoVencimientoDecision

# Parámetros Laborales
from .parametros_laborales import ParametroLaboral  # noqa: F401
globals()["ParametroLaboral"] = ParametroLaboral

# Anexos masivos
from .anexos_masivos import ProcesoAnexoMasivo, DetalleAnexoMasivo  # noqa: F401
globals()["ProcesoAnexoMasivo"] = ProcesoAnexoMasivo
globals()["DetalleAnexoMasivo"] = DetalleAnexoMasivo

# Solicitudes de Fondos - Nóminas bancarias persistentes
from .solicitudes_fondos_nominas_banco import (  # noqa: F401
    SolicitudFondosNominaBanco,
    SolicitudFondosNominaBancoDetalle,
)
globals()["SolicitudFondosNominaBanco"] = SolicitudFondosNominaBanco
globals()["SolicitudFondosNominaBancoDetalle"] = SolicitudFondosNominaBancoDetalle

# Prevención de Riesgos
from .prevencion_riesgos import (  # noqa: F401
    PrevTipoEPP,
    PrevEntregaEPP,
    PrevEntregaEPPItem,
    PrevCharlaSeguridad,
    PrevCharlaAsistente,
    PrevDocumentoPreventivo,
)
globals()["PrevTipoEPP"] = PrevTipoEPP
globals()["PrevEntregaEPP"] = PrevEntregaEPP
globals()["PrevEntregaEPPItem"] = PrevEntregaEPPItem
globals()["PrevCharlaSeguridad"] = PrevCharlaSeguridad
globals()["PrevCharlaAsistente"] = PrevCharlaAsistente
globals()["PrevDocumentoPreventivo"] = PrevDocumentoPreventivo


# Auditoría / Bitácora del sistema
from .audit import AuditLog  # noqa: F401
globals()["AuditLog"] = AuditLog

# ------------------------------------------------------------
# 3) __all__
# ------------------------------------------------------------
__all__ = sorted(
    name
    for name in globals().keys()
    if not name.startswith("_")
)