# web/app/blueprints/prevencion_riesgos/constants.py
from __future__ import annotations

ROLES_PREVENCION_VER = ("ADMIN", "OPERADOR", "REVISOR")
ROLES_PREVENCION_EDITAR = ("ADMIN", "OPERADOR")

TIPOS_CHARLA = (
    ("CHARLA_DIARIA", "Charla diaria"),
    ("CHARLA_SEMANAL", "Charla semanal"),
    ("INDUCCION_HOMBRE_NUEVO", "Inducción hombre nuevo"),
    ("ODI", "ODI / Derecho a Saber"),
    ("PROCEDIMIENTO_SEGURO", "Procedimiento seguro de trabajo"),
    ("CAPACITACION_ESPECIFICA", "Capacitación específica"),
    ("OTRO", "Otro"),
)

TIPOS_DOCUMENTO_PREVENTIVO = (
    ("ODI", "ODI / Derecho a Saber"),
    ("REGLAMENTO_INTERNO", "Registro entrega reglamento interno"),
    ("ENTREGA_EPP", "Registro entrega EPP"),
    ("EXAMEN_OCUPACIONAL", "Examen ocupacional"),
    ("CERTIFICADO_CAPACITACION", "Certificado capacitación"),
    ("TRABAJO_ALTURA", "Autorización trabajo en altura"),
    ("MANEJO_EQUIPOS", "Autorización manejo equipos"),
    ("OTRO", "Otro"),
)

ESTADOS_DOCUMENTO_PREVENTIVO = (
    ("VIGENTE", "Vigente"),
    ("POR_VENCER", "Por vencer"),
    ("VENCIDO", "Vencido"),
    ("PENDIENTE", "Pendiente"),
    ("ANULADO", "Anulado"),
)

TIPOS_EPP_INICIALES = (
    {"nombre": "Casco", "requiere_talla": False, "requiere_reposicion": True, "dias_reposicion_sugerida": 365},
    {"nombre": "Zapatos de seguridad", "requiere_talla": True, "requiere_reposicion": True, "dias_reposicion_sugerida": 180},
    {"nombre": "Guantes", "requiere_talla": True, "requiere_reposicion": True, "dias_reposicion_sugerida": 30},
    {"nombre": "Lentes de seguridad", "requiere_talla": False, "requiere_reposicion": True, "dias_reposicion_sugerida": 180},
    {"nombre": "Chaleco reflectante", "requiere_talla": True, "requiere_reposicion": True, "dias_reposicion_sugerida": 180},
    {"nombre": "Arnés de seguridad", "requiere_talla": True, "requiere_reposicion": True, "dias_reposicion_sugerida": 365},
    {"nombre": "Protección auditiva", "requiere_talla": False, "requiere_reposicion": True, "dias_reposicion_sugerida": 90},
    {"nombre": "Mascarilla / respirador", "requiere_talla": False, "requiere_reposicion": True, "dias_reposicion_sugerida": 30},
    {"nombre": "Bloqueador solar", "requiere_talla": False, "requiere_reposicion": True, "dias_reposicion_sugerida": 30},
    {"nombre": "Otro", "requiere_talla": False, "requiere_reposicion": False, "dias_reposicion_sugerida": None},
)
