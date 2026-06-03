"""add sueldos nomina y detalle

Revision ID: 74753c9aafd7
Revises: d7c64b1800a5
Create Date: 2026-02-02 21:02:57.407468

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "74753c9aafd7"
down_revision = "d7c64b1800a5"
branch_labels = None
depends_on = None


def upgrade():
    # ✅ SOLO: crear tablas de sueldos + índices

    op.create_table(
        "sueldos_nominas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("centro_costo", sa.String(length=100), nullable=False),
        sa.Column("empleador_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("origen_archivo", sa.String(length=255), nullable=True),
        sa.Column("origen", sa.String(length=30), nullable=True),
        sa.Column("importado_por", sa.Integer(), nullable=True),
        sa.Column("importado_en", sa.DateTime(), nullable=True),
        sa.Column("visado_por", sa.Integer(), nullable=True),
        sa.Column("visado_en", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["empleador_id"], ["empleadores.id"]),
        sa.ForeignKeyConstraint(["importado_por"], ["users.id"]),
        sa.ForeignKeyConstraint(["visado_por"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "anio",
            "mes",
            "centro_costo",
            "empleador_id",
            name="uq_sueldos_nominas_periodo_cc_empleador",
        ),
    )

    # Índices sueldos_nominas
    op.create_index("ix_sueldos_nominas_anio", "sueldos_nominas", ["anio"], unique=False)
    op.create_index(
        "ix_sueldos_nominas_mes", "sueldos_nominas", ["mes"], unique=False
    )
    op.create_index(
        "ix_sueldos_nominas_centro_costo",
        "sueldos_nominas",
        ["centro_costo"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_nominas_empleador_id",
        "sueldos_nominas",
        ["empleador_id"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_nominas_estado", "sueldos_nominas", ["estado"], unique=False
    )
    op.create_index(
        "ix_sueldos_nominas_periodo", "sueldos_nominas", ["anio", "mes"], unique=False
    )

    op.create_table(
        "sueldos_detalles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nomina_id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=True),
        sa.Column("contrato_id", sa.Integer(), nullable=True),
        sa.Column("obra_id", sa.Integer(), nullable=True),
        sa.Column("centro_costo", sa.String(length=100), nullable=True),
        sa.Column("rut", sa.String(length=20), nullable=True),
        sa.Column("nombre_completo", sa.String(length=255), nullable=True),
        sa.Column("nombre_obra", sa.String(length=255), nullable=True),
        sa.Column("liquido", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estado_linea", sa.String(length=30), nullable=False),
        sa.Column("observacion", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["contrato_id"], ["contratos.id"]),
        sa.ForeignKeyConstraint(["nomina_id"], ["sueldos_nominas.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "nomina_id",
            "trabajador_id",
            "contrato_id",
            name="uq_sueldos_detalles_nomina_trabajador_contrato",
        ),
    )

    # Índices sueldos_detalles
    op.create_index(
        "ix_sueldos_detalles_nomina_id",
        "sueldos_detalles",
        ["nomina_id"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_trabajador_id",
        "sueldos_detalles",
        ["trabajador_id"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_contrato_id",
        "sueldos_detalles",
        ["contrato_id"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_obra_id",
        "sueldos_detalles",
        ["obra_id"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_centro_costo",
        "sueldos_detalles",
        ["centro_costo"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_estado_linea",
        "sueldos_detalles",
        ["estado_linea"],
        unique=False,
    )
    op.create_index(
        "ix_sueldos_detalles_rut", "sueldos_detalles", ["rut"], unique=False
    )
    op.create_index(
        "ix_sueldos_detalles_nomina_obra",
        "sueldos_detalles",
        ["nomina_id", "obra_id"],
        unique=False,
    )


def downgrade():
    # ✅ SOLO: revertir tablas de sueldos + índices

    # drop índices de sueldos_detalles
    op.drop_index("ix_sueldos_detalles_nomina_obra", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_rut", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_estado_linea", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_centro_costo", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_obra_id", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_contrato_id", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_trabajador_id", table_name="sueldos_detalles")
    op.drop_index("ix_sueldos_detalles_nomina_id", table_name="sueldos_detalles")
    op.drop_table("sueldos_detalles")

    # drop índices de sueldos_nominas
    op.drop_index("ix_sueldos_nominas_periodo", table_name="sueldos_nominas")
    op.drop_index("ix_sueldos_nominas_estado", table_name="sueldos_nominas")
    op.drop_index("ix_sueldos_nominas_empleador_id", table_name="sueldos_nominas")
    op.drop_index("ix_sueldos_nominas_centro_costo", table_name="sueldos_nominas")
    op.drop_index("ix_sueldos_nominas_mes", table_name="sueldos_nominas")
    op.drop_index("ix_sueldos_nominas_anio", table_name="sueldos_nominas")
    op.drop_table("sueldos_nominas")