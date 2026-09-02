"""Record whether a chronology beat's clock time was actually published.

Only four beats in the Trishuli event have a time on the record: the 02:52 UTC
seismic signal, the 09:15 NPT surge, the Charter's 14:58 activation stamp, and
NDRRMA's 09:00 bulletin on 1 September. The rest are known to the day only.
Storing them at an invented o'clock and rendering that in a monospace time
column asserts a precision the sources do not support, so the flag travels with
the row and the desk renders date-only beats without a clock.

Revision ID: 080
Revises: 079
"""

from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "flood_chronology",
        # Defaults false: a time is a claim, and must be asserted explicitly.
        sa.Column("time_published", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("flood_chronology", "time_published")
