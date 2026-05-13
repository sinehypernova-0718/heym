"""add last_credential_id and last_model to dashboard_conversations

Revision ID: 065
Revises: 064
Create Date: 2026-05-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "065"
down_revision: str = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dashboard_conversations",
        sa.Column(
            "last_credential_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "dashboard_conversations",
        sa.Column("last_model", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dashboard_conversations", "last_model")
    op.drop_column("dashboard_conversations", "last_credential_id")
