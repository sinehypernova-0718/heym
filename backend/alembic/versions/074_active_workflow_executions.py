"""add active workflow executions registry

Revision ID: 074
Revises: 073
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "074"
down_revision: str | None = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "active_workflow_executions",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_active_workflow_executions_workflow_id",
        "active_workflow_executions",
        ["workflow_id"],
    )
    op.create_index(
        "ix_active_workflow_executions_worker_id",
        "active_workflow_executions",
        ["worker_id"],
    )
    op.create_index(
        "ix_active_workflow_executions_heartbeat_at",
        "active_workflow_executions",
        ["heartbeat_at"],
    )
    op.create_index(
        "ix_active_workflow_executions_cancel_requested_at",
        "active_workflow_executions",
        ["cancel_requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_active_workflow_executions_cancel_requested_at",
        table_name="active_workflow_executions",
    )
    op.drop_index(
        "ix_active_workflow_executions_heartbeat_at",
        table_name="active_workflow_executions",
    )
    op.drop_index(
        "ix_active_workflow_executions_worker_id",
        table_name="active_workflow_executions",
    )
    op.drop_index(
        "ix_active_workflow_executions_workflow_id",
        table_name="active_workflow_executions",
    )
    op.drop_table("active_workflow_executions")
