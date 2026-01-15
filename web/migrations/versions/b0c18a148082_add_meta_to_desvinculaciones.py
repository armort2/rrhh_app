"""add meta to desvinculaciones

Revision ID: b0c18a148082
Revises: aa3e2df5c1ee
Create Date: 2026-01-12 18:12:31.457843

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b0c18a148082'
down_revision = 'aa3e2df5c1ee'
branch_labels = None
depends_on = None


def upgrade():
    # Migración mínima y segura:
    # - NO tocar causales_termino
    # - NO tocar índices existentes
    # - En desvinculaciones: renombrar metadata -> meta si corresponde, o crear meta si no existe

    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("desvinculaciones")}

    has_meta = "meta" in cols
    has_metadata = "metadata" in cols

    # Caso ideal: ya existe meta -> no hacemos nada
    if has_meta:
        return

    # Si existe metadata (antiguo) y no meta, RENOMBRAMOS (no perdemos datos)
    if has_metadata and not has_meta:
        # PostgreSQL soporta rename column directo
        op.alter_column("desvinculaciones", "metadata", new_column_name="meta")
        return

    # Si no existe ninguna, creamos meta
    op.add_column(
        "desvinculaciones",
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade():
    # Reverso mínimo:
    # - Si existe meta, lo renombramos a metadata (para volver a la estructura anterior)
    # - Si no existía antes, igual dejarlo como metadata (comportamiento conservador)

    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("desvinculaciones")}

    has_meta = "meta" in cols
    has_metadata = "metadata" in cols

    if has_meta and not has_metadata:
        op.alter_column("desvinculaciones", "meta", new_column_name="metadata")
        return

    # Si ambos existen o no existe meta, no hacemos nada para evitar sorpresas
    return

