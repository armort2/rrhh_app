"""agregar contrato_id a prevencion riesgos

Revision ID: 6c2a9f4e8b71
Revises: 381377b5765c
Create Date: 2026-05-14 22:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "6c2a9f4e8b71"
down_revision = "381377b5765c"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------
    # prev_entregas_epp
    # ------------------------------------------------------------
    op.add_column(
        "prev_entregas_epp",
        sa.Column("contrato_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_prev_entregas_epp_contrato_id",
        "prev_entregas_epp",
        ["contrato_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_prev_entregas_epp_contrato_id_contratos",
        "prev_entregas_epp",
        "contratos",
        ["contrato_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------
    # prev_documentos_preventivos
    # ------------------------------------------------------------
    op.add_column(
        "prev_documentos_preventivos",
        sa.Column("contrato_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_prev_documentos_preventivos_contrato_id",
        "prev_documentos_preventivos",
        ["contrato_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_prev_documentos_preventivos_contrato_id_contratos",
        "prev_documentos_preventivos",
        "contratos",
        ["contrato_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------
    # prev_charla_asistentes
    # ------------------------------------------------------------
    op.add_column(
        "prev_charla_asistentes",
        sa.Column("contrato_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_prev_charla_asistentes_contrato_id",
        "prev_charla_asistentes",
        ["contrato_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_prev_charla_asistentes_contrato_id_contratos",
        "prev_charla_asistentes",
        "contratos",
        ["contrato_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # La restricción anterior impedía que un mismo trabajador apareciera
    # en una misma charla con más de un contrato. La nueva restricción
    # incorpora contrato_id para soportar escenarios multi-contrato.
    op.drop_constraint(
        "uq_prev_charla_asistente",
        "prev_charla_asistentes",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_prev_charla_asistente_contrato",
        "prev_charla_asistentes",
        ["charla_id", "trabajador_id", "contrato_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_prev_charla_asistente_contrato",
        "prev_charla_asistentes",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_prev_charla_asistente",
        "prev_charla_asistentes",
        ["charla_id", "trabajador_id"],
    )

    op.drop_constraint(
        "fk_prev_charla_asistentes_contrato_id_contratos",
        "prev_charla_asistentes",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_prev_charla_asistentes_contrato_id",
        table_name="prev_charla_asistentes",
    )
    op.drop_column("prev_charla_asistentes", "contrato_id")

    op.drop_constraint(
        "fk_prev_documentos_preventivos_contrato_id_contratos",
        "prev_documentos_preventivos",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_prev_documentos_preventivos_contrato_id",
        table_name="prev_documentos_preventivos",
    )
    op.drop_column("prev_documentos_preventivos", "contrato_id")

    op.drop_constraint(
        "fk_prev_entregas_epp_contrato_id_contratos",
        "prev_entregas_epp",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_prev_entregas_epp_contrato_id",
        table_name="prev_entregas_epp",
    )
    op.drop_column("prev_entregas_epp", "contrato_id")
