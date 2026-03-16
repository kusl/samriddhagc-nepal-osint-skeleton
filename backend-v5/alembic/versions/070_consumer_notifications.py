"""Expand notifications for consumer alerts and preferences.

Revision ID: 070
Revises: 069
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_major_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("min_severity", sa.String(length=20), nullable=False, server_default="high"),
        sa.Column("home_district", sa.String(length=80), nullable=True),
        sa.Column("followed_districts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("followed_provinces", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("followed_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[\"disasters\",\"elections\"]'::jsonb")),
        sa.Column("muted_districts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("muted_provinces", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("muted_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_notification_preferences_user_id"), "user_notification_preferences", ["user_id"], unique=True)

    op.add_column("user_notifications", sa.Column("category", sa.String(length=20), nullable=False, server_default="workflow"))
    op.add_column("user_notifications", sa.Column("severity", sa.String(length=20), nullable=True))
    op.add_column("user_notifications", sa.Column("reason_code", sa.String(length=40), nullable=True))
    op.add_column("user_notifications", sa.Column("topic_id", sa.String(length=50), nullable=True))
    op.add_column("user_notifications", sa.Column("province_name", sa.String(length=80), nullable=True))
    op.add_column("user_notifications", sa.Column("district_name", sa.String(length=80), nullable=True))
    op.add_column("user_notifications", sa.Column("source_kind", sa.String(length=30), nullable=True))
    op.add_column("user_notifications", sa.Column("source_id", sa.String(length=100), nullable=True))
    op.add_column("user_notifications", sa.Column("deeplink_url", sa.Text(), nullable=True))
    op.add_column("user_notifications", sa.Column("dedupe_key", sa.String(length=255), nullable=True))
    op.add_column("user_notifications", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_notifications", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_user_notifications_user_created", "user_notifications", ["user_id", "created_at"], unique=False)
    op.create_index("ix_user_notifications_user_type", "user_notifications", ["user_id", "type"], unique=False)
    op.create_index("ix_user_notifications_user_read", "user_notifications", ["user_id", "is_read"], unique=False)
    op.create_index("ix_user_notifications_user_dedupe", "user_notifications", ["user_id", "dedupe_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_notifications_user_dedupe", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_read", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_type", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_created", table_name="user_notifications")
    op.drop_column("user_notifications", "delivered_at")
    op.drop_column("user_notifications", "archived_at")
    op.drop_column("user_notifications", "dedupe_key")
    op.drop_column("user_notifications", "deeplink_url")
    op.drop_column("user_notifications", "source_id")
    op.drop_column("user_notifications", "source_kind")
    op.drop_column("user_notifications", "district_name")
    op.drop_column("user_notifications", "province_name")
    op.drop_column("user_notifications", "topic_id")
    op.drop_column("user_notifications", "reason_code")
    op.drop_column("user_notifications", "severity")
    op.drop_column("user_notifications", "category")

    op.drop_index(op.f("ix_user_notification_preferences_user_id"), table_name="user_notification_preferences")
    op.drop_table("user_notification_preferences")
