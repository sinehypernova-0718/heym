"""add discord_trigger credential type

Revision ID: 076_discord_trigger_credential
Revises: 075_add_discord_credential_type
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "076_discord_trigger_credential"
down_revision: str | None = "075_add_discord_credential_type"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credential_type ADD VALUE IF NOT EXISTS 'discord_trigger'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
