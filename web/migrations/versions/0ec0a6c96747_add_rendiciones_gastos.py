"""add rendiciones gastos

Revision ID: 0ec0a6c96747
Revises: 878e1a84d98c
Create Date: 2026-01-22 16:22:55.409940
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0ec0a6c96747"
down_revision = "878e1a84d98c"
branch_labels = None
depends_on = None


def upgrade():
    # --------------------------------------------------
    # Rendiciones: autorizaciones por centro de costo
    # --------------------------------------------------
    op.create_table(
        "rendiciones_cc_autorizados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("centro_costo", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "vigente",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("centro_costo", "user_id", name="uq_rendiciones_cc_user"),
    )

    op.create_index(
        "ix_rendiciones_cc_autorizados_centro_costo",
        "rendiciones_cc_autorizados",
        ["centro_costo"],
        unique=False,
    )
    op.create_index(
        "ix_rendiciones_cc_autorizados_user_id",
        "rendiciones_cc_autorizados",
        ["user_id"],
        unique=False,
    )

    # --------------------------------------------------
    # Rendiciones: cabecera
    # --------------------------------------------------
    op.create_table(
        "rendiciones_gastos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("centro_costo", sa.String(length=100), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=True),
        sa.Column("solicitud_fondos_id", sa.Integer(), nullable=True),
        sa.Column(
            "fecha_rendicion",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("periodo_desde", sa.Date(), nullable=True),
        sa.Column("periodo_hasta", sa.Date(), nullable=True),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'BORRADOR'"),
            nullable=False,
        ),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["creado_por_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["solicitud_fondos_id"], ["solicitudes_fondos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("centro_costo", "numero", name="uq_rendiciones_cc_numero"),
    )

    op.create_index(
        "ix_rendiciones_gastos_centro_costo",
        "rendiciones_gastos",
        ["centro_costo"],
        unique=False,
    )
    op.create_index(
        "ix_rendiciones_gastos_creado_por_user_id",
        "rendiciones_gastos",
        ["creado_por_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_rendiciones_gastos_estado",
        "rendiciones_gastos",
        ["estado"],
        unique=False,
    )
    op.create_index(
        "ix_rendiciones_gastos_obra_id",
        "rendiciones_gastos",
        ["obra_id"],
        unique=False,
    )
    op.create_index(
        "ix_rendiciones_gastos_solicitud_fondos_id",
        "rendiciones_gastos",
        ["solicitud_fondos_id"],
        unique=False,
    )

    # --------------------------------------------------
    # Rendiciones: ítems
    # --------------------------------------------------
    op.create_table(
        "rendiciones_gastos_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rendicion_id", sa.Integer(), nullable=False),
        sa.Column(
            "orden",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("fecha", sa.Date(), nullable=True),
        sa.Column("detalle", sa.String(length=240), nullable=False),
        sa.Column("descripcion", sa.String(length=500), nullable=True),
        sa.Column("tipo_doc", sa.String(length=30), nullable=True),
        sa.Column("nro_doc", sa.String(length=80), nullable=True),
        sa.Column("proveedor", sa.String(length=240), nullable=True),
        sa.Column(
            "monto",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["rendicion_id"],
            ["rendiciones_gastos.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_rendiciones_gastos_items_rendicion_id",
        "rendiciones_gastos_items",
        ["rendicion_id"],
        unique=False,
    )


def downgrade():
    # Orden inverso por dependencias FK
    op.drop_index(
        "ix_rendiciones_gastos_items_rendicion_id",
        table_name="rendiciones_gastos_items",
    )
    op.drop_table("rendiciones_gastos_items")

    op.drop_index(
        "ix_rendiciones_gastos_solicitud_fondos_id",
        table_name="rendiciones_gastos",
    )
    op.drop_index(
        "ix_rendiciones_gastos_obra_id",
        table_name="rendiciones_gastos",
    )
    op.drop_index(
        "ix_rendiciones_gastos_estado",
        table_name="rendiciones_gastos",
    )
    op.drop_index(
        "ix_rendiciones_gastos_creado_por_user_id",
        table_name="rendiciones_gastos",
    )
    op.drop_index(
        "ix_rendiciones_gastos_centro_costo",
        table_name="rendiciones_gastos",
    )
    op.drop_table("rendiciones_gastos")

    op.drop_index(
        "ix_rendiciones_cc_autorizados_user_id",
        table_name="rendiciones_cc_autorizados",
    )
    op.drop_index(
        "ix_rendiciones_cc_autorizados_centro_costo",
        table_name="rendiciones_cc_autorizados",
    )
    op.drop_table("rendiciones_cc_autorizados")
