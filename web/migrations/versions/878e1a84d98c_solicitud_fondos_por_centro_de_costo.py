"""solicitud fondos por centro de costo

Revision ID: 878e1a84d98c
Revises: 680b80da27f6
Create Date: 2026-01-21 14:53:04.302266

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '878e1a84d98c'
down_revision = '680b80da27f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Agregar centro_costo (por ahora nullable para poder backfillear)
    op.add_column("solicitudes_fondos", sa.Column("centro_costo", sa.String(length=100), nullable=True))

    # 2) Backfill: copiar centro_costo desde obras usando obra_id
    op.execute(
        """
        UPDATE solicitudes_fondos sf
        SET centro_costo = o.centro_costo
        FROM obras o
        WHERE sf.obra_id = o.id
        """
    )

    # 3) Asegurar no nulos (por si existiera alguna obra sin centro_costo o registros raros)
    op.execute(
        """
        UPDATE solicitudes_fondos
        SET centro_costo = 'SIN_CENTRO_COSTO'
        WHERE centro_costo IS NULL OR btrim(centro_costo) = ''
        """
    )

    # 4) Hacer centro_costo NOT NULL
    op.alter_column("solicitudes_fondos", "centro_costo", existing_type=sa.String(length=100), nullable=False)

    # 5) obra_id deja de ser obligatorio (queda como referencia opcional)
    op.alter_column("solicitudes_fondos", "obra_id", existing_type=sa.Integer(), nullable=True)

    # 6) Índice por centro_costo
    op.create_index("ix_solicitudes_fondos_centro_costo", "solicitudes_fondos", ["centro_costo"], unique=False)

    # 7) Cambiar unique: antes (obra_id, numero), ahora (centro_costo, numero)
    op.drop_constraint("uq_solicitudes_fondos_obra_numero", "solicitudes_fondos", type_="unique")
    op.create_unique_constraint("uq_solicitudes_fondos_cc_numero", "solicitudes_fondos", ["centro_costo", "numero"])


def downgrade():
    # revert unique
    op.drop_constraint("uq_solicitudes_fondos_cc_numero", "solicitudes_fondos", type_="unique")
    op.create_unique_constraint("uq_solicitudes_fondos_obra_numero", "solicitudes_fondos", ["obra_id", "numero"])

    # drop index + column
    op.drop_index("ix_solicitudes_fondos_centro_costo", table_name="solicitudes_fondos")

    # obra_id vuelve a NOT NULL
    op.alter_column("solicitudes_fondos", "obra_id", existing_type=sa.Integer(), nullable=False)

    op.drop_column("solicitudes_fondos", "centro_costo")