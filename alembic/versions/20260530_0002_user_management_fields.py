"""add user management fields and audit event types

Revision ID: 20260530_0002
Revises: 20260424_0001
Create Date: 2026-05-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0002"
down_revision = "20260424_0001"
branch_labels = None
depends_on = None

_NEW_AUDIT_VALUES = (
    "profile_updated",
    "password_changed",
    "account_deactivated",
    "session_revoked",
    "admin_user_updated",
    "admin_user_unlocked",
    "admin_sessions_revoked",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in _NEW_AUDIT_VALUES:
            op.execute(sa.text(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "display_name")
