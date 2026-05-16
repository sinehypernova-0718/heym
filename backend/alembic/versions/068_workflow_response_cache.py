"""add workflow_response_cache for cross-worker shared HTTP response cache

Revision ID: 068
Revises: 067
Create Date: 2026-05-16

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "068"
down_revision: str = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_response_cache",
        sa.Column("cache_key", sa.String(length=64), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outputs", postgresql.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_workflow_response_cache_workflow_id",
        "workflow_response_cache",
        ["workflow_id"],
    )
    op.create_index(
        "ix_workflow_response_cache_expires_at",
        "workflow_response_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_response_cache_expires_at",
        table_name="workflow_response_cache",
    )
    op.drop_index(
        "ix_workflow_response_cache_workflow_id",
        table_name="workflow_response_cache",
    )
    op.drop_table("workflow_response_cache")
