"""add descending workflow version history index

Revision ID: 066
Revises: 065
Create Date: 2026-05-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "066"
down_revision: str | None = "065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_workflow_version_desc
        ON workflow_versions (workflow_id, version_number DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_versions_workflow_version_desc")
