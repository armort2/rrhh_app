"""add horas_extras

Revision ID: 9cda4518fba2
Revises: 456f01077f93
Create Date: 2026-01-16 20:20:10.076451

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9cda4518fba2"
down_revision = "456f01077f93"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "horas_extras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trabajador_id", sa.Integer(), sa.ForeignKey("trabajadores.id"), nullable=False),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_termino", sa.Time(), nullable=False),
        sa.Column("minutos_totales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("autorizado_por", sa.String(length=120), nullable=True),
        sa.Column("observacion_revision", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("minutos_totales >= 0", name="ck_horas_extras_minutos_no_neg"),
    )

    op.create_index("ix_horas_extras_trabajador_id", "horas_extras", ["trabajador_id"], unique=False)
    op.create_index("ix_horas_extras_obra_id", "horas_extras", ["obra_id"], unique=False)
    op.create_index("ix_horas_extras_fecha", "horas_extras", ["fecha"], unique=False)
    op.create_index("ix_horas_extras_estado", "horas_extras", ["estado"], unique=False)


def downgrade():
    op.drop_index("ix_horas_extras_estado", table_name="horas_extras")
    op.drop_index("ix_horas_extras_fecha", table_name="horas_extras")
    op.drop_index("ix_horas_extras_obra_id", table_name="horas_extras")
    op.drop_index("ix_horas_extras_trabajador_id", table_name="horas_extras")
    op.drop_table("horas_extras")