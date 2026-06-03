"""sf_items_origen_sueldos_fk

Revision ID: 92461bbe77d1
Revises: 74753c9aafd7
Create Date: 2026-02-04 01:24:36.178506

"""
from alembic import op
import sqlalchemy as sa

revision = "92461bbe77d1"
down_revision = "74753c9aafd7"
branch_labels = None
depends_on = None


def upgrade():
    # 1) solicitudes_fondos_items: columnas + indices
    with op.batch_alter_table("solicitudes_fondos_items") as batch_op:
        batch_op.add_column(sa.Column("sueldo_nomina_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sueldo_detalle_id", sa.Integer(), nullable=True))

        batch_op.create_index(
            "ix_solicitudes_fondos_items_sueldo_nomina_id",
            ["sueldo_nomina_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_solicitudes_fondos_items_sueldo_detalle_id",
            ["sueldo_detalle_id"],
            unique=False,
        )

        # OJO: en Postgres, UNIQUE permite múltiples NULL. Perfecto para no bloquear items manuales.
        batch_op.create_unique_constraint(
            "uq_sf_item_sueldo_detalle",
            ["solicitud_id", "sueldo_detalle_id"],
        )

        batch_op.create_foreign_key(
            "fk_sf_items_sueldo_nomina",
            "sueldos_nominas",
            ["sueldo_nomina_id"],
            ["id"],
            ondelete="SET NULL",
        )

        batch_op.create_foreign_key(
            "fk_sf_items_sueldo_detalle",
            "sueldos_detalles",
            ["sueldo_detalle_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2) sueldos_detalles: columnas + indices
    with op.batch_alter_table("sueldos_detalles") as batch_op:
        batch_op.add_column(sa.Column("integrado_sf_item_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("integrado_en", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("integrado_por", sa.Integer(), nullable=True))

        batch_op.create_index(
            "ix_sueldos_detalles_integrado_sf_item_id",
            ["integrado_sf_item_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_sueldos_detalles_integrado_por",
            "users",
            ["integrado_por"],
            ["id"],
            ondelete="SET NULL",
        )

    # 3) FK cíclica: crearla aparte con use_alter para evitar el warning/orden de creación
    op.create_foreign_key(
        "fk_sueldos_detalles_integrado_sf_item",
        "sueldos_detalles",
        "solicitudes_fondos_items",
        ["integrado_sf_item_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )


def downgrade():
    # 1) Dropear FK cíclica primero
    op.drop_constraint(
        "fk_sueldos_detalles_integrado_sf_item",
        "sueldos_detalles",
        type_="foreignkey",
    )

    # 2) sueldos_detalles: revertir columnas/índices/FKs
    with op.batch_alter_table("sueldos_detalles") as batch_op:
        batch_op.drop_constraint("fk_sueldos_detalles_integrado_por", type_="foreignkey")
        batch_op.drop_index("ix_sueldos_detalles_integrado_sf_item_id")
        batch_op.drop_column("integrado_por")
        batch_op.drop_column("integrado_en")
        batch_op.drop_column("integrado_sf_item_id")

    # 3) solicitudes_fondos_items: revertir columnas/índices/FKs/unique
    with op.batch_alter_table("solicitudes_fondos_items") as batch_op:
        batch_op.drop_constraint("fk_sf_items_sueldo_detalle", type_="foreignkey")
        batch_op.drop_constraint("fk_sf_items_sueldo_nomina", type_="foreignkey")

        batch_op.drop_constraint("uq_sf_item_sueldo_detalle", type_="unique")

        batch_op.drop_index("ix_solicitudes_fondos_items_sueldo_detalle_id")
        batch_op.drop_index("ix_solicitudes_fondos_items_sueldo_nomina_id")

        batch_op.drop_column("sueldo_detalle_id")
        batch_op.drop_column("sueldo_nomina_id")
        
    # ### end Alembic commands ###
