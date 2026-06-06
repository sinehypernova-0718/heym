import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, status

from app.api.workflows import (
    create_workflow_share,
    list_workflow_shares,
    remove_workflow_share,
)
from app.models.schemas import WorkflowShareRequest


def _db_returning_workflow(workflow: SimpleNamespace) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=workflow))
    )
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    return db


class WorkflowSharePermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_user_cannot_list_user_shares(self) -> None:
        owner_id = uuid.uuid4()
        shared_user = SimpleNamespace(id=uuid.uuid4())
        workflow = SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id)
        db = _db_returning_workflow(workflow)

        with self.assertRaises(HTTPException) as ctx:
            await list_workflow_shares(workflow.id, current_user=shared_user, db=db)

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ctx.exception.detail, "Only owner can list shares")
        self.assertEqual(db.execute.await_count, 1)

    async def test_shared_user_cannot_create_user_share(self) -> None:
        owner_id = uuid.uuid4()
        shared_user = SimpleNamespace(id=uuid.uuid4())
        workflow = SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id)
        db = _db_returning_workflow(workflow)

        with self.assertRaises(HTTPException) as ctx:
            await create_workflow_share(
                workflow.id,
                WorkflowShareRequest(email="target@example.com"),
                current_user=shared_user,
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ctx.exception.detail, "Only owner can add shares")
        self.assertEqual(db.execute.await_count, 1)
        db.add.assert_not_called()

    async def test_shared_user_cannot_remove_user_share(self) -> None:
        owner_id = uuid.uuid4()
        shared_user = SimpleNamespace(id=uuid.uuid4())
        workflow = SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id)
        db = _db_returning_workflow(workflow)

        with self.assertRaises(HTTPException) as ctx:
            await remove_workflow_share(
                workflow.id,
                user_id=uuid.uuid4(),
                current_user=shared_user,
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ctx.exception.detail, "Only owner can remove shares")
        self.assertEqual(db.execute.await_count, 1)
        db.delete.assert_not_called()
