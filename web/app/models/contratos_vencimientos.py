# web/app/models/contratos_vencimientos.py
from __future__ import annotations

from sqlalchemy.sql import func

from ..extensions import db


class ContratoVencimientoDecision(db.Model):
    """
    Decisión operacional para un contrato próximo a vencer.
    Un registro por contrato (se actualiza en el tiempo).
    """
    __tablename__ = "contratos_vencimientos_decisiones"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(
        db.Integer,
        db.ForeignKey("contratos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Snapshot útil para filtros/reportes (redundante, pero práctico)
    obra_id = db.Column(
        db.Integer,
        db.ForeignKey("obras.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    empleador_id = db.Column(
        db.Integer,
        db.ForeignKey("empleadores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trabajador_id = db.Column(
        db.Integer,
        db.ForeignKey("trabajadores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ACCIONES:
    # - PENDIENTE: aún no deciden
    # - EXTENDER: proponen nueva fecha término
    # - TERMINAR: confirman término (opcional: fecha confirmada)
    # - INDEFINIDO: pasar a indefinido
    accion = db.Column(db.String(20), nullable=False, default="PENDIENTE", index=True)

    # Para EXTENDER
    nueva_fecha_termino = db.Column(db.Date, nullable=True)

    # Para TERMINAR (si desean confirmar una fecha distinta a la actual)
    fecha_termino_confirmada = db.Column(db.Date, nullable=True)

    comentario = db.Column(db.Text, nullable=True)

    decidido_por_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decidido_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relaciones (lazy joined para UI)
    contrato = db.relationship("Contrato", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")
    empleador = db.relationship("Empleador", lazy="joined")
    trabajador = db.relationship("Trabajador", lazy="joined")
    decidido_por = db.relationship("User", foreign_keys=[decidido_por_user_id], lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("contrato_id", name="uq_venc_decision_contrato"),
        db.CheckConstraint(
            "accion IN ('PENDIENTE','EXTENDER','TERMINAR','INDEFINIDO')",
            name="ck_venc_decision_accion",
        ),
        db.Index("ix_venc_decision_obra_accion", "obra_id", "accion"),
    )

    def __repr__(self):
        return f"<ContratoVencimientoDecision contrato={self.contrato_id} accion={self.accion}>"