"""add anexos cambio sueldo

Revision ID: e41b9c2d7a10
Revises: 92461bbe77d1
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e41b9c2d7a10"
down_revision = "92461bbe77d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anexos_cambio_sueldo_contrato",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("empleador_id", sa.Integer(), nullable=True),
        sa.Column("obra_id", sa.Integer(), nullable=True),
        sa.Column("fecha_cambio", sa.Date(), nullable=False),
        sa.Column("sueldo_base_anterior", sa.Numeric(10, 2), nullable=True),
        sa.Column("sueldo_base_nuevo", sa.Numeric(10, 2), nullable=False),
        sa.Column("asignacion_colacion_anterior", sa.Numeric(10, 2), nullable=True),
        sa.Column("asignacion_colacion_nueva", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("asignacion_movilizacion_anterior", sa.Numeric(10, 2), nullable=True),
        sa.Column("asignacion_movilizacion_nueva", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("formato", sa.String(length=10), nullable=False, server_default="AMBOS"),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="VIGENTE"),
        sa.Column("docx_nombre", sa.String(length=255), nullable=True),
        sa.Column("docx_ruta", sa.Text(), nullable=True),
        sa.Column("pdf_nombre", sa.String(length=255), nullable=True),
        sa.Column("pdf_ruta", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["contrato_id"], ["contratos.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.ForeignKeyConstraint(["empleador_id"], ["empleadores.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("anexos_cambio_sueldo_contrato", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_contrato_id"), ["contrato_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_trabajador_id"), ["trabajador_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_empleador_id"), ["empleador_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_obra_id"), ["obra_id"], unique=False)


def downgrade():
    with op.batch_alter_table("anexos_cambio_sueldo_contrato", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_obra_id"))
        batch_op.drop_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_empleador_id"))
        batch_op.drop_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_trabajador_id"))
        batch_op.drop_index(batch_op.f("ix_anexos_cambio_sueldo_contrato_contrato_id"))

    op.drop_table("anexos_cambio_sueldo_contrato")
