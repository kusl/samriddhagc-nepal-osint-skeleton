"""Create sigint_analysis table for Sonnet-level intelligence assessments.

Revision ID: 073
Revises: 072
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sigint_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_type", sa.String(length=30), nullable=False,
                   comment="market_brief, security_brief, or combined"),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=False),
        sa.Column("nepse_impact", sa.Text(), nullable=True),
        sa.Column("signals_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clusters_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sigint_analysis_type", "sigint_analysis", ["analysis_type"])
    op.create_index("ix_sigint_analysis_created_at", "sigint_analysis", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sigint_analysis_created_at", table_name="sigint_analysis")
    op.drop_index("ix_sigint_analysis_type", table_name="sigint_analysis")
    op.drop_table("sigint_analysis")
