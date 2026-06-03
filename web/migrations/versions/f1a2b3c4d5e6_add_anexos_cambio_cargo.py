"""add anexos cambio cargo

Revision ID: f1a2b3c4d5e6
Revises: e41b9c2d7a10
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e41b9c2d7a10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anexos_cambio_cargo_contrato",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("empleador_id", sa.Integer(), nullable=True),
        sa.Column("obra_id", sa.Integer(), nullable=True),
        sa.Column("fecha_cambio", sa.Date(), nullable=False),
        sa.Column("cargo_anterior_id", sa.Integer(), nullable=True),
        sa.Column("cargo_anterior_nombre", sa.String(length=150), nullable=True),
        sa.Column("cargo_nuevo_id", sa.Integer(), nullable=False),
        sa.Column("cargo_nuevo_nombre", sa.String(length=150), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("formato", sa.String(length=10), nullable=False, server_default="AMBOS"),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="VIGENTE"),
        sa.Column("docx_nombre", sa.String(length=255), nullable=True),
        sa.Column("docx_ruta", sa.Text(), nullable=True),
        sa.Column("pdf_nombre", sa.String(length=255), nullable=True),
        sa.Column("pdf_ruta", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["cargo_anterior_id"], ["cargos.id"]),
        sa.ForeignKeyConstraint(["cargo_nuevo_id"], ["cargos.id"]),
        sa.ForeignKeyConstraint(["contrato_id"], ["contratos.id"]),
        sa.ForeignKeyConstraint(["empleador_id"], ["empleadores.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_contrato_id"), "anexos_cambio_cargo_contrato", ["contrato_id"], unique=False)
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_trabajador_id"), "anexos_cambio_cargo_contrato", ["trabajador_id"], unique=False)
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_empleador_id"), "anexos_cambio_cargo_contrato", ["empleador_id"], unique=False)
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_obra_id"), "anexos_cambio_cargo_contrato", ["obra_id"], unique=False)
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_cargo_anterior_id"), "anexos_cambio_cargo_contrato", ["cargo_anterior_id"], unique=False)
    op.create_index(op.f("ix_anexos_cambio_cargo_contrato_cargo_nuevo_id"), "anexos_cambio_cargo_contrato", ["cargo_nuevo_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_cargo_nuevo_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_cargo_anterior_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_obra_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_empleador_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_trabajador_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_index(op.f("ix_anexos_cambio_cargo_contrato_contrato_id"), table_name="anexos_cambio_cargo_contrato")
    op.drop_table("anexos_cambio_cargo_contrato")
