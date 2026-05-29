"""add provider to llm pricing overrides

Revision ID: 071
Revises: 070
Create Date: 2026-05-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "071"
down_revision: str | None = "070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_pricing_override", sa.Column("provider", sa.String(50), nullable=True))
    op.execute(
        """
        UPDATE llm_pricing_override AS override
        SET
            provider = split_part(override.model, '/', 1),
            model = substring(override.model from position('/' in override.model) + 1)
        WHERE override.base_pricing_id IS NULL
          AND position('/' in override.model) > 1
          AND substring(override.model from position('/' in override.model) + 1) <> ''
          AND NOT EXISTS (
              SELECT 1
              FROM llm_pricing_override AS other
              WHERE other.user_id = override.user_id
                AND other.id <> override.id
                AND other.model = substring(override.model from position('/' in override.model) + 1)
          )
        """
    )


def downgrade() -> None:
    op.drop_column("llm_pricing_override", "provider")
