"""crear modulo prevencion riesgos

Revision ID: 381377b5765c
Revises: f1a2b3c4d5e6
Create Date: 2026-05-14 20:22:41.419127

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "381377b5765c"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prev_tipos_epp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("requiere_talla", sa.Boolean(), nullable=False),
        sa.Column("requiere_reposicion", sa.Boolean(), nullable=False),
        sa.Column("dias_reposicion_sugerida", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prev_tipos_epp_activo", "prev_tipos_epp", ["activo"], unique=False)
    op.create_index("ix_prev_tipos_epp_nombre", "prev_tipos_epp", ["nombre"], unique=True)

    op.create_table(
        "prev_charlas_seguridad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("relator", sa.String(length=150), nullable=True),
        sa.Column("duracion_minutos", sa.Integer(), nullable=True),
        sa.Column("tema", sa.Text(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("documento_nombre", sa.String(length=255), nullable=True),
        sa.Column("documento_path", sa.Text(), nullable=True),
        sa.Column("registrado_por_id", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "duracion_minutos IS NULL OR duracion_minutos > 0",
            name="ck_prev_charlas_duracion_pos",
        ),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["registrado_por_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prev_charlas_seguridad_fecha", "prev_charlas_seguridad", ["fecha"], unique=False)
    op.create_index("ix_prev_charlas_seguridad_obra_id", "prev_charlas_seguridad", ["obra_id"], unique=False)
    op.create_index(
        "ix_prev_charlas_seguridad_registrado_por_id",
        "prev_charlas_seguridad",
        ["registrado_por_id"],
        unique=False,
    )
    op.create_index("ix_prev_charlas_seguridad_tipo", "prev_charlas_seguridad", ["tipo"], unique=False)

    op.create_table(
        "prev_charla_asistentes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("charla_id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("asistio", sa.Boolean(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["charla_id"], ["prev_charlas_seguridad.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charla_id", "trabajador_id", name="uq_prev_charla_asistente"),
    )
    op.create_index("ix_prev_charla_asistentes_charla_id", "prev_charla_asistentes", ["charla_id"], unique=False)
    op.create_index(
        "ix_prev_charla_asistentes_trabajador_id",
        "prev_charla_asistentes",
        ["trabajador_id"],
        unique=False,
    )

    op.create_table(
        "prev_documentos_preventivos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=True),
        sa.Column("tipo_documento", sa.String(length=80), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("archivo_nombre", sa.String(length=255), nullable=True),
        sa.Column("archivo_path", sa.Text(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("registrado_por_id", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "estado IN ('VIGENTE', 'POR_VENCER', 'VENCIDO', 'PENDIENTE', 'ANULADO')",
            name="ck_prev_documentos_estado",
        ),
        sa.CheckConstraint(
            "fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_emision",
            name="ck_prev_documentos_vigencia",
        ),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["registrado_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prev_documentos_preventivos_estado", "prev_documentos_preventivos", ["estado"], unique=False)
    op.create_index(
        "ix_prev_documentos_preventivos_fecha_emision",
        "prev_documentos_preventivos",
        ["fecha_emision"],
        unique=False,
    )
    op.create_index(
        "ix_prev_documentos_preventivos_fecha_vencimiento",
        "prev_documentos_preventivos",
        ["fecha_vencimiento"],
        unique=False,
    )
    op.create_index("ix_prev_documentos_preventivos_obra_id", "prev_documentos_preventivos", ["obra_id"], unique=False)
    op.create_index(
        "ix_prev_documentos_preventivos_registrado_por_id",
        "prev_documentos_preventivos",
        ["registrado_por_id"],
        unique=False,
    )
    op.create_index(
        "ix_prev_documentos_preventivos_tipo_documento",
        "prev_documentos_preventivos",
        ["tipo_documento"],
        unique=False,
    )
    op.create_index(
        "ix_prev_documentos_preventivos_trabajador_id",
        "prev_documentos_preventivos",
        ["trabajador_id"],
        unique=False,
    )

    op.create_table(
        "prev_entregas_epp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("fecha_entrega", sa.Date(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("documento_nombre", sa.String(length=255), nullable=True),
        sa.Column("documento_path", sa.Text(), nullable=True),
        sa.Column("registrado_por_id", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["registrado_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prev_entregas_epp_fecha_entrega", "prev_entregas_epp", ["fecha_entrega"], unique=False)
    op.create_index("ix_prev_entregas_epp_obra_id", "prev_entregas_epp", ["obra_id"], unique=False)
    op.create_index(
        "ix_prev_entregas_epp_registrado_por_id",
        "prev_entregas_epp",
        ["registrado_por_id"],
        unique=False,
    )
    op.create_index("ix_prev_entregas_epp_trabajador_id", "prev_entregas_epp", ["trabajador_id"], unique=False)

    op.create_table(
        "prev_entrega_epp_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entrega_id", sa.Integer(), nullable=False),
        sa.Column("tipo_epp_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("talla", sa.String(length=50), nullable=True),
        sa.Column("marca_modelo", sa.String(length=150), nullable=True),
        sa.Column("fecha_reposicion_sugerida", sa.Date(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("cantidad > 0", name="ck_prev_entrega_epp_items_cantidad_pos"),
        sa.ForeignKeyConstraint(["entrega_id"], ["prev_entregas_epp.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tipo_epp_id"], ["prev_tipos_epp.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prev_entrega_epp_items_entrega_id",
        "prev_entrega_epp_items",
        ["entrega_id"],
        unique=False,
    )
    op.create_index(
        "ix_prev_entrega_epp_items_fecha_reposicion_sugerida",
        "prev_entrega_epp_items",
        ["fecha_reposicion_sugerida"],
        unique=False,
    )
    op.create_index(
        "ix_prev_entrega_epp_items_tipo_epp_id",
        "prev_entrega_epp_items",
        ["tipo_epp_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_prev_entrega_epp_items_tipo_epp_id", table_name="prev_entrega_epp_items")
    op.drop_index("ix_prev_entrega_epp_items_fecha_reposicion_sugerida", table_name="prev_entrega_epp_items")
    op.drop_index("ix_prev_entrega_epp_items_entrega_id", table_name="prev_entrega_epp_items")
    op.drop_table("prev_entrega_epp_items")

    op.drop_index("ix_prev_entregas_epp_trabajador_id", table_name="prev_entregas_epp")
    op.drop_index("ix_prev_entregas_epp_registrado_por_id", table_name="prev_entregas_epp")
    op.drop_index("ix_prev_entregas_epp_obra_id", table_name="prev_entregas_epp")
    op.drop_index("ix_prev_entregas_epp_fecha_entrega", table_name="prev_entregas_epp")
    op.drop_table("prev_entregas_epp")

    op.drop_index("ix_prev_documentos_preventivos_trabajador_id", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_tipo_documento", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_registrado_por_id", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_obra_id", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_fecha_vencimiento", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_fecha_emision", table_name="prev_documentos_preventivos")
    op.drop_index("ix_prev_documentos_preventivos_estado", table_name="prev_documentos_preventivos")
    op.drop_table("prev_documentos_preventivos")

    op.drop_index("ix_prev_charla_asistentes_trabajador_id", table_name="prev_charla_asistentes")
    op.drop_index("ix_prev_charla_asistentes_charla_id", table_name="prev_charla_asistentes")
    op.drop_table("prev_charla_asistentes")

    op.drop_index("ix_prev_charlas_seguridad_tipo", table_name="prev_charlas_seguridad")
    op.drop_index("ix_prev_charlas_seguridad_registrado_por_id", table_name="prev_charlas_seguridad")
    op.drop_index("ix_prev_charlas_seguridad_obra_id", table_name="prev_charlas_seguridad")
    op.drop_index("ix_prev_charlas_seguridad_fecha", table_name="prev_charlas_seguridad")
    op.drop_table("prev_charlas_seguridad")

    op.drop_index("ix_prev_tipos_epp_nombre", table_name="prev_tipos_epp")
    op.drop_index("ix_prev_tipos_epp_activo", table_name="prev_tipos_epp")
    op.drop_table("prev_tipos_epp")
