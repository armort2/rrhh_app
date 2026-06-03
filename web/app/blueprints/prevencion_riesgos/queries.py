# web/app/blueprints/prevencion_riesgos/queries.py
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, or_, cast, String

from ...models import (
    Contrato,
    Empleador,
    Obra,
    Trabajador,
    PrevEntregaEPP,
    PrevEntregaEPPItem,
    PrevCharlaSeguridad,
    PrevCharlaAsistente,
    PrevDocumentoPreventivo,
)


def obra_ids_accesibles(user) -> list[int] | None:
    if user and user.has_role("ADMIN"):
        return None
    return [o.id for o in getattr(user, "obras", []) or []]


def obras_accesibles_query(user):
    q = Obra.query.order_by(Obra.nombre.asc())
    ids = obra_ids_accesibles(user)
    if ids is not None:
        q = q.filter(Obra.id.in_(ids or [-1]))
    return q


def empleadores_accesibles_query(user):
    q = Empleador.query.join(Contrato, Contrato.empleador_id == Empleador.id)

    ids = obra_ids_accesibles(user)
    if ids is not None:
        q = q.filter(Contrato.obra_id.in_(ids or [-1]))

    return q.distinct().order_by(Empleador.razon_social.asc())


def trabajadores_vigentes_query(user, obra_id: int | None = None):
    q = (
        Trabajador.query
        .filter(Trabajador.estado_trabajador == "VIGENTE")
        .order_by(Trabajador.ap_paterno.asc(), Trabajador.ap_materno.asc(), Trabajador.nombres.asc())
    )

    ids = obra_ids_accesibles(user)
    if ids is not None:
        q = q.filter(Trabajador.obra_id.in_(ids or [-1]))

    if obra_id:
        q = q.filter(Trabajador.obra_id == obra_id)

    return q


def _txt(campo):
    return func.lower(func.unaccent(func.coalesce(campo, "")))


def _normalizar_busqueda(texto: str | None) -> str:
    import re
    import unicodedata

    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _tokens_busqueda(texto: str | None) -> list[str]:
    texto = _normalizar_busqueda(texto)
    if not texto:
        return []
    return [t for t in texto.replace(".", "").replace("-", "").split() if t]


def contratos_vigentes_query(
    user,
    obra_id: int | None = None,
    empleador_id: int | None = None,
    trabajador_q: str | None = None,
):
    q = Contrato.query.filter(Contrato.estado_contrato == "VIGENTE")

    ids = obra_ids_accesibles(user)
    if ids is not None:
        q = q.filter(Contrato.obra_id.in_(ids or [-1]))

    if obra_id:
        q = q.filter(Contrato.obra_id == obra_id)

    if empleador_id:
        q = q.filter(Contrato.empleador_id == empleador_id)

    tokens = _tokens_busqueda(trabajador_q)
    if tokens:
        q = q.join(Trabajador, Trabajador.id == Contrato.trabajador_id)

        for token in tokens:
            like = f"%{token}%"
            rut_limpio = func.replace(func.replace(func.coalesce(Trabajador.rut, ""), ".", ""), "-", "")

            condiciones = [
                _txt(Trabajador.nombres).ilike(like),
                _txt(Trabajador.ap_paterno).ilike(like),
                _txt(Trabajador.ap_materno).ilike(like),
                rut_limpio.ilike(like),
            ]

            if token.isdigit():
                condiciones.append(Contrato.id == int(token))
                condiciones.append(cast(Contrato.id, String).ilike(like))

            q = q.filter(or_(*condiciones))

    return q.order_by(Contrato.id.desc())


def _documentos_base_query(user):
    q = PrevDocumentoPreventivo.query.filter(PrevDocumentoPreventivo.estado != "ANULADO")
    obra_ids = obra_ids_accesibles(user)

    if obra_ids is not None:
        q = q.filter(PrevDocumentoPreventivo.obra_id.in_(obra_ids or [-1]))

    return q


def _entregas_epp_base_query(user):
    q = PrevEntregaEPP.query
    obra_ids = obra_ids_accesibles(user)

    if obra_ids is not None:
        q = q.filter(PrevEntregaEPP.obra_id.in_(obra_ids or [-1]))

    return q


def _reposiciones_epp_base_query(user):
    q = (
        PrevEntregaEPPItem.query
        .join(PrevEntregaEPP, PrevEntregaEPP.id == PrevEntregaEPPItem.entrega_id)
        .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida.isnot(None))
    )

    obra_ids = obra_ids_accesibles(user)
    if obra_ids is not None:
        q = q.filter(PrevEntregaEPP.obra_id.in_(obra_ids or [-1]))

    return q


def dashboard_counts(user) -> dict:
    today = date.today()
    in_30 = today + timedelta(days=30)

    total_contratos = contratos_vigentes_query(user).count()

    documentos_q = _documentos_base_query(user)
    epp_q = _entregas_epp_base_query(user)
    reposiciones_q = _reposiciones_epp_base_query(user)

    documentos_vencidos_q = (
        documentos_q
        .filter(PrevDocumentoPreventivo.fecha_vencimiento.isnot(None))
        .filter(PrevDocumentoPreventivo.fecha_vencimiento < today)
    )

    documentos_por_vencer_q = (
        documentos_q
        .filter(PrevDocumentoPreventivo.fecha_vencimiento.isnot(None))
        .filter(PrevDocumentoPreventivo.fecha_vencimiento >= today)
        .filter(PrevDocumentoPreventivo.fecha_vencimiento <= in_30)
    )

    reposiciones_vencidas_q = (
        reposiciones_q
        .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida < today)
    )

    reposiciones_por_vencer_q = (
        reposiciones_q
        .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida >= today)
        .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida <= in_30)
    )

    charlas_q = PrevCharlaSeguridad.query
    obra_ids = obra_ids_accesibles(user)
    if obra_ids is not None:
        charlas_q = charlas_q.filter(PrevCharlaSeguridad.obra_id.in_(obra_ids or [-1]))

    charlas_mes = (
        charlas_q
        .filter(func.date_trunc("month", PrevCharlaSeguridad.fecha) == func.date_trunc("month", func.current_date()))
        .count()
    )

    return {
        "today": today,
        "in_30": in_30,
        "total_trabajadores": total_contratos,
        "total_contratos": total_contratos,
        "documentos_vencidos": documentos_vencidos_q.count(),
        "documentos_por_vencer": documentos_por_vencer_q.count(),
        "entregas_epp": epp_q.count(),
        "charlas_mes": charlas_mes,
        "reposiciones_epp_vencidas": reposiciones_vencidas_q.count(),
        "reposiciones_epp_por_vencer": reposiciones_por_vencer_q.count(),
        "documentos_vencidos_lista": documentos_vencidos_q.order_by(PrevDocumentoPreventivo.fecha_vencimiento.asc(), PrevDocumentoPreventivo.id.desc()).limit(8).all(),
        "documentos_por_vencer_lista": documentos_por_vencer_q.order_by(PrevDocumentoPreventivo.fecha_vencimiento.asc(), PrevDocumentoPreventivo.id.desc()).limit(8).all(),
        "reposiciones_vencidas_lista": reposiciones_vencidas_q.order_by(PrevEntregaEPPItem.fecha_reposicion_sugerida.asc(), PrevEntregaEPPItem.id.desc()).limit(8).all(),
        "reposiciones_por_vencer_lista": reposiciones_por_vencer_q.order_by(PrevEntregaEPPItem.fecha_reposicion_sugerida.asc(), PrevEntregaEPPItem.id.desc()).limit(8).all(),
    }


def matriz_preventiva_rows(
    user,
    obra_id: int | None = None,
    empleador_id: int | None = None,
    trabajador_q: str | None = None,
    limit: int = 500,
) -> list[dict]:
    today = date.today()
    in_30 = today + timedelta(days=30)
    charla_reciente_desde = today - timedelta(days=30)

    contratos = (
        contratos_vigentes_query(
            user,
            obra_id=obra_id,
            empleador_id=empleador_id,
            trabajador_q=trabajador_q,
        )
        .limit(limit)
        .all()
    )

    rows = []

    for contrato in contratos:
        t = contrato.trabajador

        documentos_base = (
            PrevDocumentoPreventivo.query
            .filter(PrevDocumentoPreventivo.contrato_id == contrato.id)
            .filter(PrevDocumentoPreventivo.estado != "ANULADO")
        )

        tiene_odi = (
            documentos_base
            .filter(PrevDocumentoPreventivo.tipo_documento == "ODI")
            .first()
            is not None
        )

        documentos_vencidos = (
            documentos_base
            .filter(PrevDocumentoPreventivo.fecha_vencimiento.isnot(None))
            .filter(PrevDocumentoPreventivo.fecha_vencimiento < today)
            .count()
        )

        documentos_por_vencer = (
            documentos_base
            .filter(PrevDocumentoPreventivo.fecha_vencimiento.isnot(None))
            .filter(PrevDocumentoPreventivo.fecha_vencimiento >= today)
            .filter(PrevDocumentoPreventivo.fecha_vencimiento <= in_30)
            .count()
        )

        ultima_entrega_epp = (
            PrevEntregaEPP.query
            .filter(PrevEntregaEPP.contrato_id == contrato.id)
            .order_by(PrevEntregaEPP.fecha_entrega.desc(), PrevEntregaEPP.id.desc())
            .first()
        )

        tiene_epp = ultima_entrega_epp is not None

        reposiciones_q = (
            PrevEntregaEPPItem.query
            .join(PrevEntregaEPP, PrevEntregaEPP.id == PrevEntregaEPPItem.entrega_id)
            .filter(PrevEntregaEPP.contrato_id == contrato.id)
            .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida.isnot(None))
        )

        reposiciones_epp_vencidas = reposiciones_q.filter(PrevEntregaEPPItem.fecha_reposicion_sugerida < today).count()

        reposiciones_epp_por_vencer = (
            reposiciones_q
            .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida >= today)
            .filter(PrevEntregaEPPItem.fecha_reposicion_sugerida <= in_30)
            .count()
        )

        ultima_charla = (
            PrevCharlaSeguridad.query
            .join(PrevCharlaAsistente, PrevCharlaAsistente.charla_id == PrevCharlaSeguridad.id)
            .filter(PrevCharlaAsistente.contrato_id == contrato.id)
            .filter(PrevCharlaAsistente.asistio.is_(True))
            .order_by(PrevCharlaSeguridad.fecha.desc())
            .first()
        )

        tiene_charla_reciente = bool(ultima_charla and ultima_charla.fecha >= charla_reciente_desde)

        criticidad = 0
        if documentos_vencidos:
            criticidad += 3
        if reposiciones_epp_vencidas:
            criticidad += 3
        if not tiene_odi:
            criticidad += 2
        if not tiene_epp:
            criticidad += 2
        if documentos_por_vencer:
            criticidad += 1
        if reposiciones_epp_por_vencer:
            criticidad += 1
        if not tiene_charla_reciente:
            criticidad += 1

        if criticidad >= 3:
            estado_general = "CRITICO"
        elif criticidad >= 1:
            estado_general = "OBSERVACION"
        else:
            estado_general = "AL_DIA"

        rows.append({
            "contrato": contrato,
            "trabajador": t,
            "empleador": getattr(contrato, "empleador", None),
            "obra": getattr(contrato, "obra", None),
            "cargo": getattr(contrato, "cargo", None),
            "tiene_odi": tiene_odi,
            "tiene_epp": tiene_epp,
            "ultima_entrega_epp": ultima_entrega_epp,
            "ultima_charla": ultima_charla,
            "tiene_charla_reciente": tiene_charla_reciente,
            "documentos_vencidos": documentos_vencidos,
            "documentos_por_vencer": documentos_por_vencer,
            "reposiciones_epp_vencidas": reposiciones_epp_vencidas,
            "reposiciones_epp_por_vencer": reposiciones_epp_por_vencer,
            "criticidad": criticidad,
            "estado_general": estado_general,
        })

    rows.sort(key=lambda row: row["criticidad"], reverse=True)
    return rows
