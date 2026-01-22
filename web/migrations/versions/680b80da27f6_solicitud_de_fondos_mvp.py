"""solicitud de fondos (mvp)

Revision ID: 680b80da27f6
Revises: 942108d0ae28
Create Date: 2026-01-21 14:04:34.846304

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "680b80da27f6"
down_revision = "942108d0ae28"
branch_labels = None
depends_on = None


def upgrade():
    # ==========================
    # Solicitudes de Fondos (cabecera)
    # ==========================
    op.create_table(
        "solicitudes_fondos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha_solicitud", sa.Date(), nullable=False),
        sa.Column("periodo_tipo", sa.String(length=20), nullable=False),
        sa.Column("periodo_desde", sa.Date(), nullable=True),
        sa.Column("periodo_hasta", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('BORRADOR','ENVIADA','APROBADA','RECHAZADA','PAGADA')",
            name="ck_solicitud_fondos_estado",
        ),
        sa.CheckConstraint(
            "periodo_tipo IN ('QUINCENA','FIN_MES','OTRO')",
            name="ck_solicitud_fondos_periodo_tipo",
        ),
        sa.ForeignKeyConstraint(["creado_por_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("obra_id", "numero", name="uq_solicitudes_fondos_obra_numero"),
    )

    op.create_index(
        "ix_solicitudes_fondos_estado",
        "solicitudes_fondos",
        ["estado"],
        unique=False,
    )
    op.create_index(
        "ix_solicitudes_fondos_obra_id",
        "solicitudes_fondos",
        ["obra_id"],
        unique=False,
    )

    # ==========================
    # Solicitudes de Fondos (items)
    # ==========================
    op.create_table(
        "solicitudes_fondos_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("solicitud_id", sa.Integer(), nullable=False),
        sa.Column("seccion", sa.String(length=10), nullable=False),
        sa.Column("beneficiario_nombre", sa.String(length=200), nullable=True),
        sa.Column("beneficiario_rut_num", sa.Integer(), nullable=True),
        sa.Column("beneficiario_dv", sa.String(length=2), nullable=True),
        sa.Column("tercero_id", sa.Integer(), nullable=True),
        sa.Column("trabajador_id", sa.Integer(), nullable=True),
        sa.Column("monto", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tipo_pago", sa.String(length=40), nullable=True),
        sa.Column("nro_documento", sa.String(length=40), nullable=True),
        sa.Column("concepto", sa.String(length=80), nullable=True),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("control_interno", sa.String(length=60), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "seccion IN ('REMU','REND','TERC','VAR')",
            name="ck_solicitud_fondos_item_seccion",
        ),
        sa.CheckConstraint(
            "monto >= 0",
            name="ck_solicitud_fondos_item_monto_no_neg",
        ),
        sa.ForeignKeyConstraint(["solicitud_id"], ["solicitudes_fondos.id"]),
        sa.ForeignKeyConstraint(["tercero_id"], ["terceros.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_solicitudes_fondos_items_seccion",
        "solicitudes_fondos_items",
        ["seccion"],
        unique=False,
    )
    op.create_index(
        "ix_solicitudes_fondos_items_solicitud_id",
        "solicitudes_fondos_items",
        ["solicitud_id"],
        unique=False,
    )
    op.create_index(
        "ix_solicitudes_fondos_items_tercero_id",
        "solicitudes_fondos_items",
        ["tercero_id"],
        unique=False,
    )
    op.create_index(
        "ix_solicitudes_fondos_items_trabajador_id",
        "solicitudes_fondos_items",
        ["trabajador_id"],
        unique=False,
    )


def downgrade():
    # Nota: dropear índices explícitos antes de dropear tablas (Postgres lo soporta igual,
    # pero así queda ordenado y claro).
    op.drop_index("ix_solicitudes_fondos_items_trabajador_id", table_name="solicitudes_fondos_items")
    op.drop_index("ix_solicitudes_fondos_items_tercero_id", table_name="solicitudes_fondos_items")
    op.drop_index("ix_solicitudes_fondos_items_solicitud_id", table_name="solicitudes_fondos_items")
    op.drop_index("ix_solicitudes_fondos_items_seccion", table_name="solicitudes_fondos_items")
    op.drop_table("solicitudes_fondos_items")

    op.drop_index("ix_solicitudes_fondos_obra_id", table_name="solicitudes_fondos")
    op.drop_index("ix_solicitudes_fondos_estado", table_name="solicitudes_fondos")
    op.drop_table("solicitudes_fondos")