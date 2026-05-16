import hashlib
import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.cache_rate_limit import WorkflowResponseCacheStore


def _legacy_key(workflow_id: str, body: dict, query: dict) -> str:
    data = json.dumps({"workflow_id": workflow_id, "body": body, "query": query}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


class WorkflowResponseCacheKeyTests(unittest.TestCase):
    def test_key_matches_legacy_in_memory_scheme(self) -> None:
        store = WorkflowResponseCacheStore()
        wf = str(uuid.uuid4())
        body = {"b": 2, "a": 1}
        query = {"q": "x"}
        self.assertEqual(
            store._generate_key(wf, body, query),
            _legacy_key(wf, body, query),
        )

    def test_key_changes_with_body(self) -> None:
        store = WorkflowResponseCacheStore()
        wf = str(uuid.uuid4())
        self.assertNotEqual(
            store._generate_key(wf, {"a": 1}, {}),
            store._generate_key(wf, {"a": 2}, {}),
        )


class WorkflowResponseCacheGetTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_miss_when_no_row(self) -> None:
        store = WorkflowResponseCacheStore()
        result = SimpleNamespace(scalar_one_or_none=lambda: None)
        db = SimpleNamespace(execute=AsyncMock(return_value=result))

        hit, value = await store.get(db, str(uuid.uuid4()), {}, {})

        self.assertFalse(hit)
        self.assertIsNone(value)

    async def test_get_hit_when_not_expired(self) -> None:
        store = WorkflowResponseCacheStore()
        row = SimpleNamespace(
            outputs={"outputs": {"ok": True}},
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        result = SimpleNamespace(scalar_one_or_none=lambda: row)
        db = SimpleNamespace(execute=AsyncMock(return_value=result), delete=AsyncMock())

        hit, value = await store.get(db, str(uuid.uuid4()), {}, {})

        self.assertTrue(hit)
        self.assertEqual(value, {"outputs": {"ok": True}})
        db.delete.assert_not_called()

    async def test_get_expired_returns_miss_and_deletes(self) -> None:
        store = WorkflowResponseCacheStore()
        row = SimpleNamespace(
            outputs={"outputs": {"ok": True}},
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        result = SimpleNamespace(scalar_one_or_none=lambda: row)
        db = SimpleNamespace(execute=AsyncMock(return_value=result), delete=AsyncMock())

        hit, value = await store.get(db, str(uuid.uuid4()), {}, {})

        self.assertFalse(hit)
        self.assertIsNone(value)
        db.delete.assert_awaited_once_with(row)


class WorkflowResponseCacheSetTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_issues_upsert(self) -> None:
        store = WorkflowResponseCacheStore()
        db = SimpleNamespace(execute=AsyncMock())

        await store.set(db, str(uuid.uuid4()), {"a": 1}, {}, {"outputs": {"ok": True}}, 30)

        db.execute.assert_awaited_once()
        stmt = db.execute.await_args.args[0]
        from sqlalchemy.dialects import postgresql

        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT", compiled.upper())


class WorkflowResponseCacheCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_expired_returns_deleted_count(self) -> None:
        store = WorkflowResponseCacheStore()
        result = SimpleNamespace(rowcount=4)
        db = SimpleNamespace(execute=AsyncMock(return_value=result))

        deleted = await store.cleanup_expired(db)

        self.assertEqual(deleted, 4)
        db.execute.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
