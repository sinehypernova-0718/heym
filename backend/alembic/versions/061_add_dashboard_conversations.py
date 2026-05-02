"""add dashboard_conversations and dashboard_messages tables

Revision ID: 061
Revises: 060
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "061"
down_revision: str = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Chat"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_dashboard_conversations_user_id", "dashboard_conversations", ["user_id"])

    op.create_table(
        "dashboard_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["dashboard_conversations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_dashboard_messages_conversation_id", "dashboard_messages", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_table("dashboard_messages")
    op.drop_table("dashboard_conversations")
