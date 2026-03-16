"""Create sigint_triage table for SIGINT triage interpretations.

Revision ID: 072
Revises: 071
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "072"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sigint_triage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_title", sa.String(), nullable=False),
        sa.Column("signal_type", sa.String(length=20), nullable=False, comment="economic or security"),
        sa.Column("severity", sa.String(length=20), nullable=False, comment="HIGH or CRITICAL"),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sigint_triage_severity", "sigint_triage", ["severity"])
    op.create_index("ix_sigint_triage_signal_type", "sigint_triage", ["signal_type"])
    op.create_index("ix_sigint_triage_created_at", "sigint_triage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sigint_triage_created_at", table_name="sigint_triage")
    op.drop_index("ix_sigint_triage_signal_type", table_name="sigint_triage")
    op.drop_index("ix_sigint_triage_severity", table_name="sigint_triage")
    op.drop_table("sigint_triage")
