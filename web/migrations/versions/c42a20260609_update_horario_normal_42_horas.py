"""Actualizar Horario Normal a 42 horas semanales

Revision ID: c42a20260609
Revises: a1b2c3d4e5f7
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa


revision = "c42a20260609"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


HORARIO_NORMAL_DESC_42 = (
    "Lunes y Martes, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. "
    "Miércoles a Viernes, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 17:00 hrs."
)

HORARIO_NORMAL_DESC_44 = (
    "Lunes a jueves, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. "
    "Viernes, de 08:00 hrs. a 13:00 hrs. y de 14:00 hrs. a 17:00 hrs."
)


SQL_UP = """
WITH target AS (
    SELECT id
    FROM horarios
    WHERE nombre ILIKE '%%Horario Normal%%'
       OR descripcion ILIKE '%%Lunes a jueves, de 08:00 hrs. a 13:00 hrs.%%Viernes%%14:00 hrs. a 17:00 hrs.%%'
), deleted AS (
    DELETE FROM horario_tramos
    WHERE horario_id IN (SELECT id FROM target)
    RETURNING horario_id
), updated AS (
    UPDATE horarios
    SET descripcion = :desc_42,
        actualizado_en = NOW()
    WHERE id IN (SELECT id FROM target)
    RETURNING id
)
INSERT INTO horario_tramos (horario_id, dia_semana, hora_inicio, hora_termino, orden)
SELECT id, dia_semana, hora_inicio::time, hora_termino::time, orden
FROM updated
CROSS JOIN (VALUES
    (0, '08:00', '13:00', 1),
    (0, '14:00', '18:00', 2),
    (1, '08:00', '13:00', 1),
    (1, '14:00', '18:00', 2),
    (2, '08:00', '13:00', 1),
    (2, '14:00', '17:00', 2),
    (3, '08:00', '13:00', 1),
    (3, '14:00', '17:00', 2),
    (4, '08:00', '13:00', 1),
    (4, '14:00', '17:00', 2)
) AS v(dia_semana, hora_inicio, hora_termino, orden);
"""

SQL_DOWN = """
WITH target AS (
    SELECT id
    FROM horarios
    WHERE nombre ILIKE '%%Horario Normal%%'
       OR descripcion = :desc_42
), deleted AS (
    DELETE FROM horario_tramos
    WHERE horario_id IN (SELECT id FROM target)
    RETURNING horario_id
), updated AS (
    UPDATE horarios
    SET descripcion = :desc_44,
        actualizado_en = NOW()
    WHERE id IN (SELECT id FROM target)
    RETURNING id
)
INSERT INTO horario_tramos (horario_id, dia_semana, hora_inicio, hora_termino, orden)
SELECT id, dia_semana, hora_inicio::time, hora_termino::time, orden
FROM updated
CROSS JOIN (VALUES
    (0, '08:00', '13:00', 1),
    (0, '14:00', '18:00', 2),
    (1, '08:00', '13:00', 1),
    (1, '14:00', '18:00', 2),
    (2, '08:00', '13:00', 1),
    (2, '14:00', '18:00', 2),
    (3, '08:00', '13:00', 1),
    (3, '14:00', '18:00', 2),
    (4, '08:00', '13:00', 1),
    (4, '14:00', '17:00', 2)
) AS v(dia_semana, hora_inicio, hora_termino, orden);
"""


def upgrade():
    op.get_bind().execute(sa.text(SQL_UP), {"desc_42": HORARIO_NORMAL_DESC_42})


def downgrade():
    op.get_bind().execute(
        sa.text(SQL_DOWN),
        {"desc_42": HORARIO_NORMAL_DESC_42, "desc_44": HORARIO_NORMAL_DESC_44},
    )
