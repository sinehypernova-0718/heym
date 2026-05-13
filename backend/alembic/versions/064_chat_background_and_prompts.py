"""add chat background task fields and quick prompts table

Revision ID: 064
Revises: 063
Create Date: 2026-05-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "064"
down_revision: str = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dashboard_conversations",
        sa.Column("is_running", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "dashboard_conversations",
        sa.Column("has_unread", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "dashboard_chat_quick_prompts",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "prompts",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("dashboard_chat_quick_prompts")
    op.drop_column("dashboard_conversations", "has_unread")
    op.drop_column("dashboard_conversations", "is_running")
