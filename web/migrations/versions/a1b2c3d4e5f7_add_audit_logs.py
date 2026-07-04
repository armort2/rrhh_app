"""add audit logs

Revision ID: a1b2c3d4e5f7
Revises: 6c2a9f4e8b71
Create Date: 2026-06-03 00:20:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "6c2a9f4e8b71"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.Column("nombre", sa.String(length=120), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False, server_default="request"),
        sa.Column("section", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("endpoint", sa.String(length=160), nullable=True),
        sa.Column("blueprint", sa.String(length=80), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
    op.create_index("ix_audit_logs_username", "audit_logs", ["username"], unique=False)
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"], unique=False)
    op.create_index("ix_audit_logs_section", "audit_logs", ["section"], unique=False)
    op.create_index("ix_audit_logs_method", "audit_logs", ["method"], unique=False)
    op.create_index("ix_audit_logs_path", "audit_logs", ["path"], unique=False)
    op.create_index("ix_audit_logs_endpoint", "audit_logs", ["endpoint"], unique=False)
    op.create_index("ix_audit_logs_blueprint", "audit_logs", ["blueprint"], unique=False)
    op.create_index("ix_audit_logs_status_code", "audit_logs", ["status_code"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_created_user", "audit_logs", ["created_at", "user_id"], unique=False)
    op.create_index("ix_audit_logs_section_created", "audit_logs", ["section", "created_at"], unique=False)


def downgrade():
    op.drop_index("ix_audit_logs_section_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_user", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_status_code", table_name="audit_logs")
    op.drop_index("ix_audit_logs_blueprint", table_name="audit_logs")
    op.drop_index("ix_audit_logs_endpoint", table_name="audit_logs")
    op.drop_index("ix_audit_logs_path", table_name="audit_logs")
    op.drop_index("ix_audit_logs_method", table_name="audit_logs")
    op.drop_index("ix_audit_logs_section", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_username", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
