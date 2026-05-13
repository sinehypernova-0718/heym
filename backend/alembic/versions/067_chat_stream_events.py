"""add chat_stream_events for postgres-backed pub/sub registry

Revision ID: 067
Revises: 066
Create Date: 2026-05-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "067"
down_revision: str = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_stream_events",
        sa.Column(
            "sequence",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dashboard_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_chat_stream_events_conv_seq",
        "chat_stream_events",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_stream_events_conv_seq", table_name="chat_stream_events")
    op.drop_table("chat_stream_events")
