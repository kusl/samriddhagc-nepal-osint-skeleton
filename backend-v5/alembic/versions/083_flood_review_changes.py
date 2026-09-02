"""Review trail on flood_facts + state snapshots and change log.

Revision ID: 083
Revises: 082
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "083"
down_revision = "082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flood_facts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("flood_facts", sa.Column("reviewer", sa.String(64), nullable=True))
    op.add_column("flood_facts", sa.Column("review_note", sa.Text, nullable=True))
    op.add_column("flood_facts", sa.Column("review_reason", sa.String(32), nullable=True))
    op.add_column("flood_facts", sa.Column("original", postgresql.JSONB, nullable=True))
    op.create_table(
        "flood_state_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False, index=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_flood_state_kind_key_taken", "flood_state_snapshots", ["kind", "key", "taken_at"])
    op.create_table(
        "flood_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False, index=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False, server_default="info"),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("before", postgresql.JSONB, nullable=True),
        sa.Column("after", postgresql.JSONB, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channels", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("flood_changes")
    op.drop_index("ix_flood_state_kind_key_taken", table_name="flood_state_snapshots")
    op.drop_table("flood_state_snapshots")
    for c in ("original", "review_reason", "review_note", "reviewer", "reviewed_at"):
        op.drop_column("flood_facts", c)
