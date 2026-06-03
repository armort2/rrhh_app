"""create desvinculacion_doc_inputs table

Revision ID: d7c64b1800a5
Revises: 3823802a0074
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d7c64b1800a5"
down_revision = "3823802a0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "desvinculacion_doc_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("desvinculacion_id", sa.Integer(), nullable=False),
        sa.Column("doc_tipo", sa.String(length=30), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["desvinculacion_id"],
            ["desvinculaciones.id"],
            name="fk_desv_doc_inputs_desvinculacion_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("desvinculacion_id", "doc_tipo", name="uq_desv_doc_inputs_desv_tipo"),
    )

    op.create_index(
        "ix_desv_doc_inputs_desvinculacion_id",
        "desvinculacion_doc_inputs",
        ["desvinculacion_id"],
    )
    op.create_index(
        "ix_desv_doc_inputs_doc_tipo",
        "desvinculacion_doc_inputs",
        ["doc_tipo"],
    )


def downgrade() -> None:
    op.drop_index("ix_desv_doc_inputs_doc_tipo", table_name="desvinculacion_doc_inputs")
    op.drop_index("ix_desv_doc_inputs_desvinculacion_id", table_name="desvinculacion_doc_inputs")
    op.drop_table("desvinculacion_doc_inputs")