"""Add cabinet 100-day action tracker tables.

Revision ID: 076
Revises: 075
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cabinet_action_programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_key", sa.String(length=80), nullable=False),
        sa.Column("title_ne", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("source_pdf_name", sa.String(length=255), nullable=True),
        sa.Column("source_pdf_path", sa.Text(), nullable=True),
        sa.Column("source_pdf_hash", sa.String(length=128), nullable=True),
        sa.Column("approval_date_bs", sa.String(length=20), nullable=False),
        sa.Column("approval_date_ad", sa.Date(), nullable=False),
        sa.Column("source_language", sa.String(length=12), nullable=False, server_default="ne"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_key"),
    )
    op.create_index("ix_cabinet_action_programs_program_key", "cabinet_action_programs", ["program_key"], unique=False)

    op.create_table(
        "cabinet_action_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_number", sa.Integer(), nullable=False),
        sa.Column("section_key", sa.String(length=80), nullable=False),
        sa.Column("section_title_ne", sa.Text(), nullable=True),
        sa.Column("section_title_en", sa.Text(), nullable=True),
        sa.Column("source_text_ne", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=False),
        sa.Column("lead_institution", sa.String(length=255), nullable=True),
        sa.Column("supporting_institutions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("action_type", sa.String(length=80), nullable=True),
        sa.Column("trackability_class", sa.String(length=40), nullable=False),
        sa.Column("deadline_text_ne", sa.Text(), nullable=True),
        sa.Column("deadline_kind", sa.String(length=30), nullable=True),
        sa.Column("deadline_value", sa.Float(), nullable=True),
        sa.Column("due_date_bs", sa.String(length=40), nullable=True),
        sa.Column("due_date_ad", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="announced"),
        sa.Column("evidence_strength", sa.String(length=40), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_pdf_page", sa.Integer(), nullable=True),
        sa.Column("notes_internal", sa.Text(), nullable=True),
        sa.Column("raw_seed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["program_id"], ["cabinet_action_programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "item_number", name="uq_cabinet_action_program_item"),
    )
    op.create_index("ix_cabinet_action_items_program_id", "cabinet_action_items", ["program_id"], unique=False)
    op.create_index("ix_cabinet_action_items_section_key", "cabinet_action_items", ["section_key"], unique=False)
    op.create_index("ix_cabinet_action_items_lead_institution", "cabinet_action_items", ["lead_institution"], unique=False)
    op.create_index("ix_cabinet_action_items_action_type", "cabinet_action_items", ["action_type"], unique=False)
    op.create_index("ix_cabinet_action_items_trackability_class", "cabinet_action_items", ["trackability_class"], unique=False)
    op.create_index("ix_cabinet_action_items_due_date_ad", "cabinet_action_items", ["due_date_ad"], unique=False)
    op.create_index("ix_cabinet_action_items_status", "cabinet_action_items", ["status"], unique=False)
    op.create_index("ix_cabinet_action_items_is_public", "cabinet_action_items", ["is_public"], unique=False)
    op.create_index("idx_cabinet_action_section_status", "cabinet_action_items", ["section_key", "status"], unique=False)

    op.create_table(
        "cabinet_action_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_order", sa.Integer(), nullable=False),
        sa.Column("source_text_ne", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=False),
        sa.Column("deadline_text_ne", sa.Text(), nullable=True),
        sa.Column("deadline_kind", sa.String(length=30), nullable=True),
        sa.Column("deadline_value", sa.Float(), nullable=True),
        sa.Column("due_date_bs", sa.String(length=40), nullable=True),
        sa.Column("due_date_ad", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="announced"),
        sa.Column("evidence_strength", sa.String(length=40), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes_internal", sa.Text(), nullable=True),
        sa.Column("raw_seed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_id"], ["cabinet_action_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "milestone_order", name="uq_cabinet_action_item_milestone_order"),
    )
    op.create_index("ix_cabinet_action_milestones_item_id", "cabinet_action_milestones", ["item_id"], unique=False)
    op.create_index("ix_cabinet_action_milestones_due_date_ad", "cabinet_action_milestones", ["due_date_ad"], unique=False)
    op.create_index("ix_cabinet_action_milestones_status", "cabinet_action_milestones", ["status"], unique=False)

    op.create_table(
        "cabinet_action_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cabinet_action_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False, server_default="approved"),
        sa.Column("final_section_key", sa.String(length=80), nullable=True),
        sa.Column("final_section_title_en", sa.Text(), nullable=True),
        sa.Column("final_title_en", sa.Text(), nullable=True),
        sa.Column("final_summary_en", sa.Text(), nullable=True),
        sa.Column("final_lead_institution", sa.String(length=255), nullable=True),
        sa.Column("final_supporting_institutions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_action_type", sa.String(length=80), nullable=True),
        sa.Column("final_trackability_class", sa.String(length=40), nullable=True),
        sa.Column("final_status", sa.String(length=40), nullable=True),
        sa.Column("final_evidence_note", sa.Text(), nullable=True),
        sa.Column("final_confidence", sa.Float(), nullable=True),
        sa.Column("final_is_public", sa.Boolean(), nullable=True),
        sa.Column("final_manifesto_promise_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("milestone_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("needs_rerun", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rerun_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rerun_requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cabinet_action_item_id"], ["cabinet_action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rerun_requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cabinet_action_item_id"),
    )
    op.create_index("ix_cabinet_action_reviews_cabinet_action_item_id", "cabinet_action_reviews", ["cabinet_action_item_id"], unique=False)
    op.create_index("ix_cabinet_action_reviews_workflow_status", "cabinet_action_reviews", ["workflow_status"], unique=False)

    op.create_table(
        "cabinet_action_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_story_id", sa.String(length=64), nullable=True),
        sa.Column("source_announcement_id", sa.String(length=64), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("extracted_status", sa.String(length=40), nullable=True),
        sa.Column("evidence_note_en", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("raw_model_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_id"], ["cabinet_action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["cabinet_action_milestones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cabinet_action_evidence_item_id", "cabinet_action_evidence", ["item_id"], unique=False)
    op.create_index("ix_cabinet_action_evidence_milestone_id", "cabinet_action_evidence", ["milestone_id"], unique=False)
    op.create_index("ix_cabinet_action_evidence_published_at", "cabinet_action_evidence", ["published_at"], unique=False)

    op.create_table(
        "cabinet_action_promise_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifesto_promise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_id"], ["cabinet_action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manifesto_promise_id"], ["manifesto_promises.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "manifesto_promise_id", name="uq_cabinet_action_promise_link"),
    )
    op.create_index("ix_cabinet_action_promise_links_item_id", "cabinet_action_promise_links", ["item_id"], unique=False)
    op.create_index("ix_cabinet_action_promise_links_manifesto_promise_id", "cabinet_action_promise_links", ["manifesto_promise_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cabinet_action_promise_links_manifesto_promise_id", table_name="cabinet_action_promise_links")
    op.drop_index("ix_cabinet_action_promise_links_item_id", table_name="cabinet_action_promise_links")
    op.drop_table("cabinet_action_promise_links")

    op.drop_index("ix_cabinet_action_evidence_published_at", table_name="cabinet_action_evidence")
    op.drop_index("ix_cabinet_action_evidence_milestone_id", table_name="cabinet_action_evidence")
    op.drop_index("ix_cabinet_action_evidence_item_id", table_name="cabinet_action_evidence")
    op.drop_table("cabinet_action_evidence")

    op.drop_index("ix_cabinet_action_reviews_workflow_status", table_name="cabinet_action_reviews")
    op.drop_index("ix_cabinet_action_reviews_cabinet_action_item_id", table_name="cabinet_action_reviews")
    op.drop_table("cabinet_action_reviews")

    op.drop_index("ix_cabinet_action_milestones_status", table_name="cabinet_action_milestones")
    op.drop_index("ix_cabinet_action_milestones_due_date_ad", table_name="cabinet_action_milestones")
    op.drop_index("ix_cabinet_action_milestones_item_id", table_name="cabinet_action_milestones")
    op.drop_table("cabinet_action_milestones")

    op.drop_index("idx_cabinet_action_section_status", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_is_public", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_status", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_due_date_ad", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_trackability_class", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_action_type", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_lead_institution", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_section_key", table_name="cabinet_action_items")
    op.drop_index("ix_cabinet_action_items_program_id", table_name="cabinet_action_items")
    op.drop_table("cabinet_action_items")

    op.drop_index("ix_cabinet_action_programs_program_key", table_name="cabinet_action_programs")
    op.drop_table("cabinet_action_programs")
