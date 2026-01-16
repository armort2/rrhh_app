"""restore contratos_import

Revision ID: 456f01077f93
Revises: 546182cf4817
Create Date: 2026-01-13 15:09:24.799394

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '456f01077f93'
down_revision = '546182cf4817'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contratos_import',
        sa.Column('id', sa.Integer(), primary_key=True),  # ✅ PK
        sa.Column('rut_sin_dv', sa.VARCHAR(length=20), nullable=False),
        sa.Column('empleador_id', sa.INTEGER(), nullable=True),
        sa.Column('obra_id', sa.INTEGER(), nullable=True),
        sa.Column('cargo_id', sa.INTEGER(), nullable=True),
        sa.Column('tipo_contrato', sa.VARCHAR(length=30), nullable=True),
        sa.Column('fecha_inicio', sa.DATE(), nullable=True),
        sa.Column('fecha_termino', sa.DATE(), nullable=True),
        sa.Column('jornada', sa.TEXT(), nullable=True),
        sa.Column('horas_semanales', sa.INTEGER(), nullable=True),
        sa.Column('sueldo_base', sa.NUMERIC(precision=10, scale=2), nullable=True),
        sa.Column('asignacion_movilizacion', sa.NUMERIC(precision=10, scale=2), nullable=True),
        sa.Column('asignacion_colacion', sa.NUMERIC(precision=10, scale=2), nullable=True),
        sa.Column('asignacion_herramientas', sa.NUMERIC(precision=10, scale=2), nullable=True),
        sa.Column('estado_contrato', sa.VARCHAR(length=20), nullable=False),
        sa.Column('causal_termino', sa.VARCHAR(length=250), nullable=True),
        sa.Column('fecha_finiquito', sa.DATE(), nullable=True),
        sa.Column('horario_id', sa.INTEGER(), nullable=True),
    )

    # Índices sugeridos (opcionales pero recomendables)
    op.create_index('ix_contratos_import_rut_sin_dv', 'contratos_import', ['rut_sin_dv'])
    op.create_index('ix_contratos_import_empleador_id', 'contratos_import', ['empleador_id'])
    op.create_index('ix_contratos_import_obra_id', 'contratos_import', ['obra_id'])
    op.create_index('ix_contratos_import_cargo_id', 'contratos_import', ['cargo_id'])


def downgrade():
    op.drop_index('ix_contratos_import_cargo_id', table_name='contratos_import')
    op.drop_index('ix_contratos_import_obra_id', table_name='contratos_import')
    op.drop_index('ix_contratos_import_empleador_id', table_name='contratos_import')
    op.drop_index('ix_contratos_import_rut_sin_dv', table_name='contratos_import')
    op.drop_table('contratos_import')
