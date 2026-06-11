"""add discord credential type

Revision ID: 075_add_discord_credential_type
Revises: 074
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "075_add_discord_credential_type"
down_revision: str | None = "074"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credential_type ADD VALUE IF NOT EXISTS 'discord'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    pass
