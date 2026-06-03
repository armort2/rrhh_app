"""add requiere_carta y carta_template a causales_termino

Revision ID: 3823802a0074
Revises: 0ec0a6c96747
Create Date: 2026-01-27 17:41:10.370283

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3823802a0074"
down_revision = "0ec0a6c96747"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Columnas nuevas (solo esta tabla)
    op.add_column(
        "causales_termino",
        sa.Column("requiere_carta", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "causales_termino",
        sa.Column("carta_template", sa.String(length=120), nullable=True),
    )

    # 2) Datos iniciales (según tus plantillas)
    op.execute("""
        UPDATE public.causales_termino
        SET requiere_carta = false,
            carta_template = NULL
        WHERE id = 2;
    """)

    op.execute("UPDATE public.causales_termino SET carta_template = '1.docx' WHERE id = 1;")
    op.execute("UPDATE public.causales_termino SET carta_template = '4.docx' WHERE id = 4;")
    op.execute("UPDATE public.causales_termino SET carta_template = '7.docx' WHERE id = 7;")
    op.execute("UPDATE public.causales_termino SET carta_template = '8.docx' WHERE id = 8;")

    # 3) Constraint de consistencia
    op.create_check_constraint(
        "ck_causales_carta_template",
        "causales_termino",
        "(requiere_carta = false AND carta_template IS NULL) OR (requiere_carta = true)",
    )

    # 4) Quitamos el default “pegado” en la BD (solo era para el backfill)
    op.alter_column("causales_termino", "requiere_carta", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_causales_carta_template", "causales_termino", type_="check")
    op.drop_column("causales_termino", "carta_template")
    op.drop_column("causales_termino", "requiere_carta")