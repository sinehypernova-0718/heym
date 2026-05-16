import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkflowResponseCache


class WorkflowResponseCacheStore:
    """Postgres-backed cache for workflow HTTP/curl endpoint responses.

    Shared across all uvicorn workers (an in-process dict only hit when the
    repeat request happened to land on the same worker).
    """

    def _generate_key(self, workflow_id: str, body: dict, query: dict) -> str:
        data = json.dumps(
            {"workflow_id": workflow_id, "body": body, "query": query}, sort_keys=True
        )
        return hashlib.sha256(data.encode()).hexdigest()

    async def get(
        self, db: AsyncSession, workflow_id: str, body: dict, query: dict
    ) -> tuple[bool, Any]:
        key = self._generate_key(workflow_id, body, query)
        result = await db.execute(
            select(WorkflowResponseCache).where(WorkflowResponseCache.cache_key == key)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False, None

        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            await db.delete(row)
            return False, None

        return True, row.outputs

    async def set(
        self,
        db: AsyncSession,
        workflow_id: str,
        body: dict,
        query: dict,
        value: Any,
        ttl_seconds: int,
    ) -> None:
        key = self._generate_key(workflow_id, body, query)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        stmt = (
            pg_insert(WorkflowResponseCache)
            .values(
                cache_key=key,
                workflow_id=uuid.UUID(str(workflow_id)),
                outputs=value,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=["cache_key"],
                set_={
                    "outputs": value,
                    "expires_at": expires_at,
                    "workflow_id": uuid.UUID(str(workflow_id)),
                },
            )
        )
        await db.execute(stmt)

    async def cleanup_expired(self, db: AsyncSession) -> int:
        result = await db.execute(
            delete(WorkflowResponseCache).where(
                WorkflowResponseCache.expires_at < datetime.now(timezone.utc)
            )
        )
        return result.rowcount or 0


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = {}
        self._lock = Lock()

    def _generate_key(self, workflow_id: str, client_ip: str) -> str:
        return f"{workflow_id}:{client_ip}"

    def is_allowed(
        self, workflow_id: str, client_ip: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int, int]:
        key = self._generate_key(workflow_id, client_ip)
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            if key not in self._requests:
                self._requests[key] = []

            self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]

            current_count = len(self._requests[key])
            remaining = max(0, max_requests - current_count)

            if current_count >= max_requests:
                if self._requests[key]:
                    oldest = min(self._requests[key])
                    retry_after = int(oldest + window_seconds - now) + 1
                else:
                    retry_after = window_seconds
                return False, remaining, retry_after

            self._requests[key].append(now)
            return True, remaining - 1, 0

    def cleanup_expired(self, max_window_seconds: int = 3600) -> int:
        now = time.time()
        cutoff = now - max_window_seconds
        removed = 0
        with self._lock:
            empty_keys = []
            for key, timestamps in self._requests.items():
                self._requests[key] = [ts for ts in timestamps if ts > cutoff]
                if not self._requests[key]:
                    empty_keys.append(key)
            for key in empty_keys:
                del self._requests[key]
                removed += 1
        return removed


response_cache = WorkflowResponseCacheStore()
rate_limiter = InMemoryRateLimiter()
