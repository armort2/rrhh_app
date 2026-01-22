"""terceros timestamps not null

Revision ID: 942108d0ae28
Revises: 9ee58531ff30
Create Date: 2026-01-20 21:01:13.118679

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '942108d0ae28'
down_revision = '9ee58531ff30'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Backfill defensivo por si existiera algún NULL
    op.execute("UPDATE terceros SET creado_en = NOW() WHERE creado_en IS NULL;")
    op.execute("UPDATE terceros SET actualizado_en = NOW() WHERE actualizado_en IS NULL;")

    # 2) Asegurar defaults a nivel BD (consistente)
    op.alter_column(
        "terceros",
        "creado_en",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    op.alter_column(
        "terceros",
        "actualizado_en",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def downgrade():
    # Volvemos a permitir NULL (y no forzamos default)
    op.alter_column(
        "terceros",
        "actualizado_en",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        nullable=True,
    )
    op.alter_column(
        "terceros",
        "creado_en",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        nullable=True,
    )