"""add terceros

Revision ID: 9ee58531ff30
Revises: 9cda4518fba2
Create Date: 2026-01-20 20:25:36.354418

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9ee58531ff30'
down_revision = '9cda4518fba2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "terceros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rut_num", sa.Integer(), nullable=False),
        sa.Column("dv", sa.String(length=2), nullable=False),
        sa.Column("ap_paterno", sa.String(length=200), nullable=False),
        sa.Column("ap_materno", sa.String(length=200), nullable=True),
        sa.Column("nombres", sa.String(length=200), nullable=True),
        sa.Column("correo", sa.String(length=150), nullable=True),
        sa.Column("banco_id", sa.Integer(), nullable=True),
        sa.Column("cuenta_numero", sa.String(length=80), nullable=True),
        sa.Column("rut_cta_num", sa.Integer(), nullable=True),
        sa.Column("rut_cta_dv", sa.String(length=2), nullable=True),
        sa.Column("estado", sa.String(length=20), server_default="VIGENTE", nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["banco_id"], ["bancos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rut_num"),
    )
    op.create_index("ix_terceros_estado", "terceros", ["estado"], unique=False)
    op.create_index("ix_terceros_rut_num", "terceros", ["rut_num"], unique=False)


def downgrade():
    op.drop_index("ix_terceros_rut_num", table_name="terceros")
    op.drop_index("ix_terceros_estado", table_name="terceros")
    op.drop_table("terceros")