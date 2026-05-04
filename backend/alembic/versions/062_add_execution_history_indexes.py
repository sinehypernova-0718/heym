"""add indexes to execution_history for all-history query performance

Revision ID: 062
Revises: 061
Create Date: 2026-05-04
"""

import sqlalchemy as sa

from alembic import op

revision: str = "062"
down_revision: str = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_execution_history_started_at",
        "execution_history",
        [sa.text("started_at DESC")],
    )
    op.create_index("ix_execution_history_status", "execution_history", ["status"])
    op.create_index("ix_execution_history_trigger_source", "execution_history", ["trigger_source"])
    # Composite index for the common case: filter by workflow_id + sort by started_at
    op.create_index(
        "ix_execution_history_workflow_started_at",
        "execution_history",
        ["workflow_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_history_workflow_started_at", table_name="execution_history")
    op.drop_index("ix_execution_history_trigger_source", table_name="execution_history")
    op.drop_index("ix_execution_history_status", table_name="execution_history")
    op.drop_index("ix_execution_history_started_at", table_name="execution_history")
