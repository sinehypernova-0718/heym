# Multi-MCP Server (Named Clusters) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named MCP server clustering so users can create multiple isolated MCP servers (each with UUID URL + independent API key) pointing Claude/Cursor at different workflow subsets, while leaving `/api/mcp/*` untouched.

**Architecture:** New `MCPServer` DB entity and `MCPServerWorkflow` join table. A new FastAPI router at `/api/mcp/servers` handles CRUD + MCP protocol endpoints per server. `MCPSessionStore` is extended (backward-compatibly) to carry an optional `server_id` alongside `user_id`. Frontend MCPPanel grows a "Named Servers" accordion below the existing single-server UI.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Alembic, Vue 3 + TypeScript strict, Pinia

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/db/models.py` | Add `MCPServer`, `MCPServerWorkflow` models; `User.mcp_servers` relationship |
| Create | `backend/alembic/versions/063_add_mcp_servers.py` | DB migration: two new tables |
| Modify | `backend/app/models/schemas.py` | Add `MCPServerCreate`, `MCPServerResponse`, `MCPServerListResponse`, `MCPServerWorkflowToggleRequest` |
| Modify | `backend/app/services/mcp_session.py` | Extend `_MCPSession`, `create()`, `resolve()` to carry optional `server_id` |
| Modify | `backend/app/api/mcp.py` | Update line 70 to unpack new tuple from `resolve()` |
| Create | `backend/app/api/mcp_servers.py` | New router: CRUD + SSE/message/tools protocol endpoints |
| Modify | `backend/app/main.py` | Register new router at `/api/mcp/servers` |
| Create | `backend/tests/test_mcp_servers.py` | All unit tests |
| Modify | `frontend/src/services/api.ts` | Add `MCPServerItem` interface + `mcpServersApi` |
| Modify | `frontend/src/components/MCP/MCPPanel.vue` | Add Named Servers accordion section |

---

## Task 1: Add MCPServer and MCPServerWorkflow DB models

**Files:**
- Modify: `backend/app/db/models.py` (after line 120, before `class Team`)

- [ ] **Step 1: Write a failing import test**

Create `backend/tests/test_mcp_server_models.py`:

```python
import unittest
from app.db.models import MCPServer, MCPServerWorkflow


class MCPServerModelImportTests(unittest.TestCase):
    def test_mcp_server_model_importable(self) -> None:
        assert MCPServer.__tablename__ == "mcp_servers"

    def test_mcp_server_workflow_model_importable(self) -> None:
        assert MCPServerWorkflow.__tablename__ == "mcp_server_workflows"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_mcp_server_models.py -v
```

Expected: `ImportError: cannot import name 'MCPServer'`

- [ ] **Step 3: Add models to `backend/app/db/models.py`**

Insert after line 120 (after the last `team_memberships` relationship on `User`), before `class Team`:

First, add `mcp_servers` relationship to the `User` class — append after line 120:

```python
    mcp_servers: Mapped[list["MCPServer"]] = relationship(
        "MCPServer", back_populates="owner", cascade="all, delete-orphan"
    )
```

Then add the two new model classes after the closing of the `User` class (before `class Team`):

```python
class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship("User", back_populates="mcp_servers")
    server_workflows: Mapped[list["MCPServerWorkflow"]] = relationship(
        "MCPServerWorkflow", back_populates="server", cascade="all, delete-orphan"
    )


class MCPServerWorkflow(Base):
    __tablename__ = "mcp_server_workflows"

    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True
    )

    server: Mapped["MCPServer"] = relationship("MCPServer", back_populates="server_workflows")
    workflow: Mapped["Workflow"] = relationship("Workflow")
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd backend && uv run pytest tests/test_mcp_server_models.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/test_mcp_server_models.py
git commit -m "feat: add MCPServer and MCPServerWorkflow DB models"
```

---

## Task 2: Create Alembic migration 063

**Files:**
- Create: `backend/alembic/versions/063_add_mcp_servers.py`

- [ ] **Step 1: Create the migration file**

```python
"""add mcp_servers tables

Revision ID: 063
Revises: 062
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_key", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mcp_servers_user_id", "mcp_servers", ["user_id"])
    op.create_index("ix_mcp_servers_api_key", "mcp_servers", ["api_key"], unique=True)

    op.create_table(
        "mcp_server_workflows",
        sa.Column(
            "mcp_server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("mcp_server_workflows")
    op.drop_index("ix_mcp_servers_api_key", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_user_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")
```

- [ ] **Step 2: Run migration**

```bash
cd backend && uv run alembic upgrade head
```

Expected: migration runs without error, `063` applied.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/063_add_mcp_servers.py
git commit -m "feat: add Alembic migration 063 for mcp_servers tables"
```

---

## Task 3: Add Pydantic schemas for named MCP servers

**Files:**
- Modify: `backend/app/models/schemas.py` (insert after line 869, after `MCPRegenerateKeyResponse`)

- [ ] **Step 1: Insert schemas**

Add after `class MCPRegenerateKeyResponse` (after line 869):

```python
class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class MCPServerWorkflowToggleRequest(BaseModel):
    enabled: bool


class MCPServerResponse(BaseModel):
    id: uuid.UUID
    name: str
    api_key: str
    created_at: datetime
    workflow_ids: list[uuid.UUID] = Field(default_factory=list)


class MCPServerListResponse(BaseModel):
    servers: list[MCPServerResponse] = Field(default_factory=list)
```

Also verify `datetime` is imported at the top of `schemas.py`. If not present, add `from datetime import datetime` to its imports.

- [ ] **Step 2: Verify import**

```bash
cd backend && uv run python -c "from app.models.schemas import MCPServerCreate, MCPServerResponse, MCPServerListResponse, MCPServerWorkflowToggleRequest; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/schemas.py
git commit -m "feat: add Pydantic schemas for named MCP servers"
```

---

## Task 4: Extend MCPSessionStore to carry server_id

**Files:**
- Modify: `backend/app/services/mcp_session.py`
- Modify: `backend/app/api/mcp.py` (line 70)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_mcp_session_store.py`:

```python
import unittest
from app.services.mcp_session import MCPSessionStore


class MCPSessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MCPSessionStore()

    def test_create_without_server_id_resolves_to_none_server_id(self) -> None:
        token = self.store.create("user-123")
        result = self.store.resolve(token)
        self.assertIsNotNone(result)
        user_id, server_id = result
        self.assertEqual(user_id, "user-123")
        self.assertIsNone(server_id)

    def test_create_with_server_id_resolves_correctly(self) -> None:
        token = self.store.create("user-456", server_id="server-abc")
        result = self.store.resolve(token)
        self.assertIsNotNone(result)
        user_id, server_id = result
        self.assertEqual(user_id, "user-456")
        self.assertEqual(server_id, "server-abc")

    def test_resolve_unknown_token_returns_none(self) -> None:
        self.assertIsNone(self.store.resolve("nonexistent-token"))

    def test_revoke_makes_token_invalid(self) -> None:
        token = self.store.create("user-789")
        self.store.revoke(token)
        self.assertIsNone(self.store.resolve(token))
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_mcp_session_store.py -v
```

Expected: `TypeError` or `AssertionError` — resolve returns `str`, not tuple.

- [ ] **Step 3: Update `_MCPSession` dataclass and `MCPSessionStore` in `backend/app/services/mcp_session.py`**

Replace the entire file with:

```python
"""Short-lived MCP SSE session tokens.

When a client connects to the SSE endpoint it is issued a short-lived,
single-use session token that is embedded in the message endpoint URL
instead of the actual MCP API key or OAuth bearer token.  This avoids
leaking long-lived credentials in server access logs.
"""

import secrets
import threading
import time
from dataclasses import dataclass, field

_SESSION_TTL_SECONDS = 3600  # 1 hour
_CLEANUP_INTERVAL_SECONDS = 600


@dataclass
class _MCPSession:
    user_id: str
    created_at: float
    server_id: str | None = field(default=None)


class MCPSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _MCPSession] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL_SECONDS:
            return
        expired = [
            k for k, s in self._sessions.items() if now - s.created_at > _SESSION_TTL_SECONDS
        ]
        for k in expired:
            del self._sessions[k]
        self._last_cleanup = now

    def create(self, user_id: str, server_id: str | None = None) -> str:
        """Create a new session token mapped to user_id (and optionally server_id)."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._cleanup(now)
            self._sessions[token] = _MCPSession(
                user_id=user_id, created_at=now, server_id=server_id
            )
        return token

    def resolve(self, token: str) -> tuple[str, str | None] | None:
        """Return (user_id, server_id) for a valid non-expired token, or None."""
        now = time.time()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if now - session.created_at > _SESSION_TTL_SECONDS:
                del self._sessions[token]
                return None
            return session.user_id, session.server_id

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)


mcp_session_store = MCPSessionStore()
```

- [ ] **Step 4: Update `mcp.py` line 70 to unpack the tuple**

In `backend/app/api/mcp.py`, replace lines 70–71:

```python
        user_id_str = mcp_session_store.resolve(session_param)
        if user_id_str is None:
```

with:

```python
        resolve_result = mcp_session_store.resolve(session_param)
        if resolve_result is None:
            user_id_str = None
        else:
            user_id_str, _ = resolve_result  # ignore server_id for default server
        if user_id_str is None:
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_mcp_session_store.py tests/test_mcp_workflow_traces.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/mcp_session.py backend/app/api/mcp.py backend/tests/test_mcp_session_store.py
git commit -m "feat: extend MCPSessionStore to carry optional server_id"
```

---

## Task 5: Create mcp_servers.py — CRUD endpoints

**Files:**
- Create: `backend/app/api/mcp_servers.py`
- Create: `backend/tests/test_mcp_servers.py`

- [ ] **Step 1: Write failing CRUD tests**

Create `backend/tests/test_mcp_servers.py`:

```python
import secrets
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.mcp_servers import (
    create_mcp_server,
    delete_mcp_server,
    list_mcp_servers,
    regenerate_server_key,
    toggle_server_workflow,
)
from app.models.schemas import MCPServerCreate, MCPServerWorkflowToggleRequest


def _make_server(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Test Server",
        api_key=secrets.token_urlsafe(48),
        created_at=datetime.now(timezone.utc),
    )


def _make_workflow(owner_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="My Workflow",
    )


class MCPServerCreateTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_server_returns_server_with_api_key(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        added_server: list = []

        db = AsyncMock()
        db.add = MagicMock(side_effect=lambda obj: added_server.append(obj))
        db.commit = AsyncMock()

        async def mock_refresh(obj: object) -> None:
            obj.id = server_id  # type: ignore[attr-defined]
            obj.created_at = now  # type: ignore[attr-defined]

        db.refresh = mock_refresh

        result = await create_mcp_server(
            body=MCPServerCreate(name="CRM Tools"),
            current_user=user,
            db=db,
        )

        self.assertEqual(result.name, "CRM Tools")
        self.assertTrue(result.api_key)
        self.assertEqual(result.id, server_id)
        self.assertEqual(len(result.workflow_ids), 0)
        db.commit.assert_called_once()


class MCPServerListTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_returns_only_user_servers(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server = _make_server(user.id)

        db = AsyncMock()
        # First execute: list servers; second execute: workflow_ids per server
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[server])))),
                MagicMock(all=MagicMock(return_value=[])),
            ]
        )

        result = await list_mcp_servers(current_user=user, db=db)
        self.assertEqual(len(result.servers), 1)
        self.assertEqual(result.servers[0].name, "Test Server")


class MCPServerDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_existing_server(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server = _make_server(user.id)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=server))
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()

        await delete_mcp_server(server_id=server.id, current_user=user, db=db)

        db.delete.assert_called_once_with(server)
        db.commit.assert_called_once()

    async def test_delete_nonexistent_server_raises_404(self) -> None:
        from fastapi import HTTPException

        user = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with self.assertRaises(HTTPException) as ctx:
            await delete_mcp_server(server_id=uuid.uuid4(), current_user=user, db=db)

        self.assertEqual(ctx.exception.status_code, 404)


class MCPServerToggleWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_add_creates_join_row(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server = _make_server(user.id)
        workflow = _make_workflow(user.id)

        db = AsyncMock()
        # execute calls: 1=find server, 2=find workflow, 3=find existing join row
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=server)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=workflow)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # no existing row
            ]
        )
        db.add = MagicMock()
        db.commit = AsyncMock()

        await toggle_server_workflow(
            server_id=server.id,
            workflow_id=workflow.id,
            body=MCPServerWorkflowToggleRequest(enabled=True),
            current_user=user,
            db=db,
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_toggle_remove_deletes_join_row(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server = _make_server(user.id)
        workflow = _make_workflow(user.id)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=server)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=workflow)),
                MagicMock(),  # delete result
            ]
        )
        db.commit = AsyncMock()

        await toggle_server_workflow(
            server_id=server.id,
            workflow_id=workflow.id,
            body=MCPServerWorkflowToggleRequest(enabled=False),
            current_user=user,
            db=db,
        )

        db.commit.assert_called_once()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_mcp_servers.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'create_mcp_server' from 'app.api.mcp_servers'`

- [ ] **Step 3: Create `backend/app/api/mcp_servers.py` with CRUD handlers**

```python
import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.mcp import (
    _add_mcp_workflow_trace,
    get_credentials_context_for_user,
    workflow_to_mcp_tool,
)
from app.api.workflows import collect_referenced_workflows
from app.db.models import (
    ExecutionHistory,
    MCPServer,
    MCPServerWorkflow,
    OAuthAccessToken,
    User,
    Workflow,
)
from app.db.session import get_db
from app.models.schemas import (
    MCPInitializeResult,
    MCPJSONRPCRequest,
    MCPServerCreate,
    MCPServerListResponse,
    MCPServerResponse,
    MCPServerWorkflowToggleRequest,
    MCPTextContent,
    MCPToolResult,
    MCPToolsListResponse,
)
from app.services.execution_cancellation import (
    clear_execution as clear_active_execution,
)
from app.services.execution_cancellation import register_execution
from app.services.global_variables_service import get_global_variables_context
from app.services.mcp_session import mcp_session_store
from app.services.workflow_executor import execute_workflow
from app.api.workflows import _persist_global_variables_from_execution
from app.api.analytics import upsert_workflow_analytics_snapshot

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_server_for_user(
    db: AsyncSession, server_id: uuid.UUID, user_id: uuid.UUID
) -> MCPServer:
    result = await db.execute(
        select(MCPServer).where(MCPServer.id == server_id, MCPServer.user_id == user_id)
    )
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


async def _get_server_workflow_ids(db: AsyncSession, server_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(MCPServerWorkflow.workflow_id).where(
            MCPServerWorkflow.mcp_server_id == server_id
        )
    )
    return [row[0] for row in result.all()]


async def _get_server_workflows(db: AsyncSession, server_id: uuid.UUID) -> list[Workflow]:
    result = await db.execute(
        select(Workflow)
        .join(MCPServerWorkflow, MCPServerWorkflow.workflow_id == Workflow.id)
        .where(MCPServerWorkflow.mcp_server_id == server_id)
    )
    return list(result.scalars().all())


def _sanitize_tool_name(name: str) -> str:
    n = name.lower().replace(" ", "_").replace("-", "_")
    return "".join(c if c.isalnum() or c == "_" else "" for c in n)


# ---------------------------------------------------------------------------
# Auth dependency for MCP protocol endpoints (SSE / message / tools)
# ---------------------------------------------------------------------------


async def _get_named_server_context(
    server_id: uuid.UUID,
    request: Request,
    x_mcp_key: str | None = Header(None, alias="X-MCP-Key"),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, MCPServer]:
    # 0. Short-lived session token
    session_param = request.query_params.get("session")
    if session_param:
        resolve_result = mcp_session_store.resolve(session_param)
        if resolve_result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session token",
            )
        user_id_str, sess_server_id = resolve_result
        if sess_server_id != str(server_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session token not valid for this server",
            )
        user_res = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
        user = user_res.scalar_one_or_none()
        server_res = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
        server = server_res.scalar_one_or_none()
        if user is None or server is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User or server not found")
        return user, server

    # 1. OAuth Bearer token
    auth_header = request.headers.get("Authorization", "")
    token_param = request.query_params.get("token")
    bearer_token: str | None = None
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:]
    elif token_param:
        bearer_token = token_param

    if bearer_token:
        now = datetime.now(timezone.utc)
        token_res = await db.execute(
            select(OAuthAccessToken).where(
                OAuthAccessToken.access_token == bearer_token,
                OAuthAccessToken.revoked.is_(False),
                OAuthAccessToken.expires_at > now,
            )
        )
        token_record = token_res.scalar_one_or_none()
        if token_record is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_res = await db.execute(select(User).where(User.id == token_record.user_id))
        user = user_res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        server_res = await db.execute(
            select(MCPServer).where(MCPServer.id == server_id, MCPServer.user_id == user.id)
        )
        server = server_res.scalar_one_or_none()
        if server is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user, server

    # 2. Per-server API key
    api_key = x_mcp_key or request.query_params.get("key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication. Provide Authorization: Bearer <token> or X-MCP-Key header",
            headers={"WWW-Authenticate": 'Bearer realm="heym-mcp"'},
        )
    server_res = await db.execute(
        select(MCPServer).where(MCPServer.api_key == api_key, MCPServer.id == server_id)
    )
    server = server_res.scalar_one_or_none()
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    user_res = await db.execute(select(User).where(User.id == server.user_id))
    user = user_res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user, server


# ---------------------------------------------------------------------------
# CRUD endpoints (JWT auth via get_current_user)
# ---------------------------------------------------------------------------


@router.get("", response_model=MCPServerListResponse)
async def list_mcp_servers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPServerListResponse:
    result = await db.execute(
        select(MCPServer)
        .where(MCPServer.user_id == current_user.id)
        .order_by(MCPServer.created_at)
    )
    servers = list(result.scalars().all())
    items = []
    for s in servers:
        workflow_ids = await _get_server_workflow_ids(db, s.id)
        items.append(
            MCPServerResponse(
                id=s.id,
                name=s.name,
                api_key=s.api_key,
                created_at=s.created_at,
                workflow_ids=workflow_ids,
            )
        )
    return MCPServerListResponse(servers=items)


@router.post("", response_model=MCPServerResponse, status_code=201)
async def create_mcp_server(
    body: MCPServerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPServerResponse:
    server = MCPServer(
        user_id=current_user.id,
        name=body.name,
        api_key=secrets.token_urlsafe(48),
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        api_key=server.api_key,
        created_at=server.created_at,
        workflow_ids=[],
    )


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    server = await _fetch_server_for_user(db, server_id, current_user.id)
    await db.delete(server)
    await db.commit()


@router.post("/{server_id}/regenerate-key", response_model=MCPServerResponse)
async def regenerate_server_key(
    server_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPServerResponse:
    server = await _fetch_server_for_user(db, server_id, current_user.id)
    server.api_key = secrets.token_urlsafe(48)
    await db.commit()
    await db.refresh(server)
    workflow_ids = await _get_server_workflow_ids(db, server.id)
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        api_key=server.api_key,
        created_at=server.created_at,
        workflow_ids=workflow_ids,
    )


@router.patch("/{server_id}/workflows/{workflow_id}")
async def toggle_server_workflow(
    server_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: MCPServerWorkflowToggleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _fetch_server_for_user(db, server_id, current_user.id)

    wf_res = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id, Workflow.owner_id == current_user.id
        )
    )
    if wf_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if body.enabled:
        existing = await db.execute(
            select(MCPServerWorkflow).where(
                MCPServerWorkflow.mcp_server_id == server_id,
                MCPServerWorkflow.workflow_id == workflow_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(MCPServerWorkflow(mcp_server_id=server_id, workflow_id=workflow_id))
            await db.commit()
    else:
        await db.execute(
            delete(MCPServerWorkflow).where(
                MCPServerWorkflow.mcp_server_id == server_id,
                MCPServerWorkflow.workflow_id == workflow_id,
            )
        )
        await db.commit()

    return {"enabled": body.enabled}
```

- [ ] **Step 4: Run CRUD tests**

```bash
cd backend && uv run pytest tests/test_mcp_servers.py -v
```

Expected: all CRUD tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/mcp_servers.py backend/tests/test_mcp_servers.py
git commit -m "feat: add named MCP server CRUD endpoints and tests"
```

---

## Task 6: Add MCP protocol endpoints (SSE, message, tools) to mcp_servers.py

**Files:**
- Modify: `backend/app/api/mcp_servers.py` (append)
- Modify: `backend/tests/test_mcp_servers.py` (append)

- [ ] **Step 1: Write failing protocol tests**

Append to `backend/tests/test_mcp_servers.py`:

```python
from app.api.mcp_servers import list_named_server_tools, handle_named_server_message
from app.services.workflow_executor import ExecutionResult


def _make_execution_result(workflow_id: uuid.UUID) -> ExecutionResult:
    return ExecutionResult(
        workflow_id=workflow_id,
        status="success",
        outputs={"result": "ok"},
        execution_time_ms=10.0,
        node_results=[],
        sub_workflow_executions=[],
    )


class MCPServerToolsListTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_list_returns_only_server_workflows(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        server = _make_server(user.id)
        workflow = SimpleNamespace(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="CRM Sync",
            description="Syncs CRM",
            nodes=[{"id": "n1", "type": "manual", "data": {}}],
            edges=[],
        )

        db = AsyncMock()

        with patch(
            "app.api.mcp_servers._get_server_workflows", AsyncMock(return_value=[workflow])
        ):
            result = await list_named_server_tools(server=(user, server), db=db)

        self.assertEqual(len(result.tools), 1)
        self.assertEqual(result.tools[0].name, "crm_sync")


class MCPServerAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_api_key_raises_401(self) -> None:
        from fastapi import HTTPException
        from app.api.mcp_servers import _get_named_server_context
        from fastapi import Request

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/mcp/servers/xxx/sse",
                "headers": [(b"x-mcp-key", b"wrong-key")],
                "query_string": b"",
            }
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with self.assertRaises(HTTPException) as ctx:
            await _get_named_server_context(
                server_id=uuid.uuid4(),
                request=request,
                x_mcp_key="wrong-key",
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_session_token_wrong_server_raises_403(self) -> None:
        from fastapi import HTTPException
        from app.api.mcp_servers import _get_named_server_context
        from fastapi import Request
        from app.services.mcp_session import mcp_session_store

        user_id = str(uuid.uuid4())
        other_server_id = str(uuid.uuid4())
        token = mcp_session_store.create(user_id, server_id=other_server_id)

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/mcp/servers/xxx/sse",
                "headers": [],
                "query_string": f"session={token}".encode(),
            }
        )

        db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            await _get_named_server_context(
                server_id=uuid.uuid4(),  # different server
                request=request,
                x_mcp_key=None,
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 403)


class MCPServerDefaultUnaffectedTests(unittest.IsolatedAsyncioTestCase):
    def test_default_server_session_has_none_server_id(self) -> None:
        from app.services.mcp_session import mcp_session_store

        token = mcp_session_store.create("user-abc")
        result = mcp_session_store.resolve(token)
        self.assertIsNotNone(result)
        user_id, server_id = result
        self.assertEqual(user_id, "user-abc")
        self.assertIsNone(server_id)
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd backend && uv run pytest tests/test_mcp_servers.py::MCPServerToolsListTests tests/test_mcp_servers.py::MCPServerAuthTests -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'list_named_server_tools'`

- [ ] **Step 3: Append protocol endpoints to `backend/app/api/mcp_servers.py`**

```python
# ---------------------------------------------------------------------------
# MCP Protocol endpoints (SSE, message, tools) — named server
# ---------------------------------------------------------------------------


@router.get("/{server_id}/tools", response_model=MCPToolsListResponse)
async def list_named_server_tools(
    server: tuple[User, MCPServer] = Depends(_get_named_server_context),
    db: AsyncSession = Depends(get_db),
) -> MCPToolsListResponse:
    _, mcp_server = server
    workflows = await _get_server_workflows(db, mcp_server.id)
    tools = [workflow_to_mcp_tool(w) for w in workflows]
    return MCPToolsListResponse(tools=tools)


@router.get("/{server_id}/sse")
async def named_server_sse(
    server_id: uuid.UUID,
    request: Request,
    server: tuple[User, MCPServer] = Depends(_get_named_server_context),
) -> StreamingResponse:
    user, mcp_server = server
    session_token = mcp_session_store.create(str(user.id), server_id=str(mcp_server.id))
    base_url = str(request.base_url).rstrip("/")
    message_endpoint = f"{base_url}/api/mcp/servers/{server_id}/message?session={session_token}"

    async def event_generator() -> asyncio.AsyncGenerator[str, None]:
        yield f"event: endpoint\ndata: {message_endpoint}\n\n"
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{server_id}/message")
async def handle_named_server_message(
    server_id: uuid.UUID,
    request: Request,
    server: tuple[User, MCPServer] = Depends(_get_named_server_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = await request.json()
    msg = MCPJSONRPCRequest(**body)
    user, mcp_server = server

    if msg.id is None:
        if msg.method == "notifications/initialized":
            return {"jsonrpc": "2.0"}
        return {"jsonrpc": "2.0"}

    if msg.method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg.id,
            "result": MCPInitializeResult().model_dump(),
        }

    if msg.method == "tools/list":
        workflows = await _get_server_workflows(db, mcp_server.id)
        tools = [workflow_to_mcp_tool(w) for w in workflows]
        return {
            "jsonrpc": "2.0",
            "id": msg.id,
            "result": {"tools": [t.model_dump() for t in tools]},
        }

    if msg.method == "tools/call":
        tool_name = msg.params.get("name", "")
        arguments = msg.params.get("arguments", {})

        workflows = await _get_server_workflows(db, mcp_server.id)
        target_workflow = None
        for w in workflows:
            if _sanitize_tool_name(w.name) == tool_name:
                target_workflow = w
                break

        if target_workflow is None:
            return {
                "jsonrpc": "2.0",
                "id": msg.id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }

        if not target_workflow.nodes:
            return {
                "jsonrpc": "2.0",
                "id": msg.id,
                "error": {"code": -32602, "message": "Workflow has no nodes"},
            }

        enriched_inputs = {"headers": {}, "query": {}, "body": arguments}
        workflow_cache = await collect_referenced_workflows(db, target_workflow.nodes)
        credentials_context = await get_credentials_context_for_user(db, user.id)
        global_variables_context = await get_global_variables_context(db, user.id)

        execution_id = uuid.uuid4()
        cancel_event = register_execution(
            workflow_id=target_workflow.id, execution_id=execution_id
        )
        try:
            execution_result = await asyncio.to_thread(
                execute_workflow,
                workflow_id=target_workflow.id,
                nodes=target_workflow.nodes,
                edges=target_workflow.edges,
                inputs=enriched_inputs,
                workflow_cache=workflow_cache,
                test_run=False,
                credentials_context=credentials_context,
                global_variables_context=global_variables_context,
                trace_user_id=user.id,
                cancel_event=cancel_event,
            )

            history_entry = ExecutionHistory(
                workflow_id=target_workflow.id,
                inputs=enriched_inputs,
                outputs=execution_result.outputs,
                node_results=execution_result.node_results,
                status=execution_result.status,
                execution_time_ms=execution_result.execution_time_ms,
                trigger_source="MCP",
            )
            db.add(history_entry)

            await upsert_workflow_analytics_snapshot(
                db,
                workflow_id=target_workflow.id,
                owner_id=target_workflow.owner_id,
                workflow_name_snapshot=target_workflow.name,
                status=execution_result.status,
                execution_time_ms=execution_result.execution_time_ms,
            )

            for sub_exec in execution_result.sub_workflow_executions:
                sub_history = ExecutionHistory(
                    workflow_id=uuid.UUID(sub_exec.workflow_id),
                    inputs=sub_exec.inputs,
                    outputs=sub_exec.outputs,
                    node_results=sub_exec.node_results,
                    status=sub_exec.status,
                    execution_time_ms=sub_exec.execution_time_ms,
                    trigger_source=sub_exec.trigger_source,
                )
                db.add(sub_history)

            await _persist_global_variables_from_execution(
                db,
                user.id,
                target_workflow.nodes,
                workflow_cache,
                execution_result.node_results,
                execution_result.sub_workflow_executions,
            )

            _add_mcp_workflow_trace(
                db,
                user_id=user.id,
                workflow=target_workflow,
                tool_name=tool_name,
                arguments=arguments,
                execution_result=execution_result,
            )
            await db.flush()

            output_text = json.dumps(execution_result.outputs, indent=2, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": msg.id,
                "result": {
                    "content": [{"type": "text", "text": output_text}],
                    "isError": execution_result.status == "error",
                },
            }
        except Exception as e:
            _add_mcp_workflow_trace(
                db,
                user_id=user.id,
                workflow=target_workflow,
                tool_name=tool_name,
                arguments=arguments,
                execution_result=None,
                error=str(e),
            )
            await db.flush()
            return {
                "jsonrpc": "2.0",
                "id": msg.id,
                "result": {
                    "content": [{"type": "text", "text": f"Execution error: {e}"}],
                    "isError": True,
                },
            }
        finally:
            clear_active_execution(execution_id)

    return {
        "jsonrpc": "2.0",
        "id": msg.id,
        "error": {"code": -32601, "message": f"Method not found: {msg.method}"},
    }
```

- [ ] **Step 4: Run all mcp_servers tests**

```bash
cd backend && uv run pytest tests/test_mcp_servers.py tests/test_mcp_session_store.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/mcp_servers.py backend/tests/test_mcp_servers.py
git commit -m "feat: add named MCP server SSE, message, and tools protocol endpoints"
```

---

## Task 7: Register router in main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add import**

In `backend/app/main.py`, find the imports section where `from app.api import (...)` is. Add `mcp_servers` to that import block.

- [ ] **Step 2: Register router after line 210**

After:
```python
app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP"])
```

Add:
```python
app.include_router(mcp_servers.router, prefix="/api/mcp/servers", tags=["MCP Servers"])
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend && ./run_tests.sh
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register named MCP server router at /api/mcp/servers"
```

---

## Task 8: Frontend — add TypeScript types and API client

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add `MCPServerItem` interface**

In `frontend/src/services/api.ts`, after the `MCPRegenerateKeyResponse` interface (around line 1416), add:

```typescript
export interface MCPServerItem {
  id: string;
  name: string;
  api_key: string;
  created_at: string;
  workflow_ids: string[];
}

export interface MCPServerListResponse {
  servers: MCPServerItem[];
}
```

- [ ] **Step 2: Add `mcpServersApi` object**

After the closing brace of `mcpApi`, add:

```typescript
export const mcpServersApi = {
  list: async (): Promise<MCPServerListResponse> => {
    const response = await api.get<MCPServerListResponse>("/mcp/servers");
    return response.data;
  },

  create: async (name: string): Promise<MCPServerItem> => {
    const response = await api.post<MCPServerItem>("/mcp/servers", { name });
    return response.data;
  },

  delete: async (serverId: string): Promise<void> => {
    await api.delete(`/mcp/servers/${serverId}`);
  },

  regenerateKey: async (serverId: string): Promise<MCPServerItem> => {
    const response = await api.post<MCPServerItem>(
      `/mcp/servers/${serverId}/regenerate-key`,
    );
    return response.data;
  },

  toggleWorkflow: async (
    serverId: string,
    workflowId: string,
    enabled: boolean,
  ): Promise<void> => {
    await api.patch(`/mcp/servers/${serverId}/workflows/${workflowId}`, {
      enabled,
    });
  },
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add MCPServerItem types and mcpServersApi client"
```

---

## Task 9: Frontend — MCPPanel Named Servers section

**Files:**
- Modify: `frontend/src/components/MCP/MCPPanel.vue`

- [ ] **Step 1: Add reactive state to `<script setup>`**

In the `<script setup>` section, add after the existing imports:

```typescript
import { mcpServersApi, type MCPServerItem, type MCPWorkflowItem } from "@/services/api";
```

Add to the reactive state block:

```typescript
const namedServers = ref<MCPServerItem[]>([]);
const expandedServer = ref<string | null>(null);
const newServerName = ref("");
const creatingServer = ref(false);
const allWorkflows = ref<MCPWorkflowItem[]>([]);
```

- [ ] **Step 2: Add methods**

After `loadConfig()`, add:

```typescript
async function loadNamedServers(): Promise<void> {
  const data = await mcpServersApi.list();
  namedServers.value = data.servers;
}

async function createServer(): Promise<void> {
  if (!newServerName.value.trim()) return;
  creatingServer.value = true;
  try {
    const server = await mcpServersApi.create(newServerName.value.trim());
    namedServers.value.push(server);
    newServerName.value = "";
    expandedServer.value = server.id;
  } finally {
    creatingServer.value = false;
  }
}

async function deleteServer(serverId: string): Promise<void> {
  await mcpServersApi.delete(serverId);
  namedServers.value = namedServers.value.filter((s) => s.id !== serverId);
  if (expandedServer.value === serverId) expandedServer.value = null;
}

async function toggleServerWorkflow(
  serverId: string,
  workflowId: string,
  currentlyEnabled: boolean,
): Promise<void> {
  await mcpServersApi.toggleWorkflow(serverId, workflowId, !currentlyEnabled);
  const server = namedServers.value.find((s) => s.id === serverId);
  if (!server) return;
  if (!currentlyEnabled) {
    server.workflow_ids = [...server.workflow_ids, workflowId];
  } else {
    server.workflow_ids = server.workflow_ids.filter((id) => id !== workflowId);
  }
}

function serverSseUrl(serverId: string): string {
  return `${window.location.origin}/api/mcp/servers/${serverId}/sse`;
}
```

Update `loadConfig()` to also load named servers and allWorkflows:

```typescript
async function loadConfig(): Promise<void> {
  loading.value = true;
  try {
    config.value = await mcpApi.getConfig();
    allWorkflows.value = config.value.workflows;
    await loadNamedServers();
  } finally {
    loading.value = false;
  }
}
```

- [ ] **Step 3: Add Named Servers template section**

In the `<template>`, append the following after the closing tag of the existing workflow/config section and before the final closing `</div>`:

```html
<!-- Named MCP Servers -->
<div class="mt-6 border-t pt-4">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-sm font-semibold">Named MCP Servers</h3>
    <div class="flex gap-2">
      <input
        v-model="newServerName"
        type="text"
        placeholder="Server name…"
        class="text-xs border rounded px-2 py-1 w-36"
        @keydown.enter="createServer"
      />
      <button
        class="text-xs px-2 py-1 rounded bg-primary text-primary-foreground"
        :disabled="creatingServer || !newServerName.trim()"
        @click="createServer"
      >
        + New
      </button>
    </div>
  </div>

  <div v-if="namedServers.length === 0" class="text-xs text-muted-foreground">
    No named servers yet. Create one above to cluster your workflows.
  </div>

  <div v-for="server in namedServers" :key="server.id" class="mb-2 border rounded">
    <div
      class="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-muted/50"
      @click="expandedServer = expandedServer === server.id ? null : server.id"
    >
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">{{ server.name }}</span>
        <span class="text-xs text-muted-foreground">{{ server.workflow_ids.length }} workflows</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="text-xs text-muted-foreground hover:text-destructive"
          @click.stop="deleteServer(server.id)"
        >
          Delete
        </button>
      </div>
    </div>

    <div v-if="expandedServer === server.id" class="border-t px-3 py-3 space-y-3">
      <!-- SSE URL -->
      <div>
        <p class="text-xs text-muted-foreground mb-1">SSE Endpoint</p>
        <div class="flex items-center gap-2">
          <code class="text-xs bg-muted px-2 py-1 rounded flex-1 truncate">
            {{ serverSseUrl(server.id) }}
          </code>
          <button class="text-xs" @click="copyToClipboard(serverSseUrl(server.id), 'URL')">
            Copy
          </button>
        </div>
      </div>

      <!-- API Key -->
      <div>
        <p class="text-xs text-muted-foreground mb-1">API Key</p>
        <div class="flex items-center gap-2">
          <code class="text-xs bg-muted px-2 py-1 rounded flex-1">
            {{ server.api_key.slice(0, 8) }}…{{ server.api_key.slice(-4) }}
          </code>
          <button class="text-xs" @click="copyToClipboard(server.api_key, 'API key')">
            Copy
          </button>
        </div>
      </div>

      <!-- Workflow assignment grid -->
      <div>
        <p class="text-xs text-muted-foreground mb-2">Workflows</p>
        <div class="space-y-1">
          <div
            v-for="wf in allWorkflows"
            :key="wf.id"
            class="flex items-center justify-between text-xs py-1"
          >
            <span>{{ wf.name }}</span>
            <button
              :class="
                server.workflow_ids.includes(wf.id)
                  ? 'text-primary font-medium'
                  : 'text-muted-foreground'
              "
              @click="toggleServerWorkflow(server.id, wf.id, server.workflow_ids.includes(wf.id))"
            >
              {{ server.workflow_ids.includes(wf.id) ? "Enabled" : "Add" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Verify lint and typecheck**

```bash
cd frontend && bun run lint && bun run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MCP/MCPPanel.vue
git commit -m "feat: add Named Servers section to MCPPanel"
```

---

## Task 10: Run full check and documentation

- [ ] **Step 1: Run full check suite**

```bash
cd /path/to/heymrun && ./check.sh
```

Expected: ruff format + lint + all tests pass.

- [ ] **Step 2: Commit any ruff formatting diffs**

```bash
git add -u && git commit -m "style: apply ruff formatting"
```

(Skip if no changes.)

- [ ] **Step 3: Update documentation via heym-documentation skill**

Invoke the `heym-documentation` skill to update MCP docs with:
- New "Named MCP Servers" section
- Server creation flow
- UUID URL format (`/api/mcp/servers/{uuid}/sse`)
- Per-server API key usage
- Backward compatibility note (existing `/api/mcp/sse` unchanged)
