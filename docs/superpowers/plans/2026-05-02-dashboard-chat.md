# Dashboard Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent multi-session dashboard chat with unique URLs, collapsible sidebar, rename/pin/delete, and LLM streaming.

**Architecture:** New `ChatsView.vue` at `/chats` and `/chats/:id` renders a collapsible `ChatListPanel` (left) and `ChatConversation` (right). A Pinia `chatStore` manages state with localStorage persistence for sidebar visibility. The backend adds two new tables (`dashboard_conversations`, `dashboard_messages`) with six endpoints including SSE streaming for LLM responses via `AsyncOpenAI`.

**Tech Stack:** Vue 3 + TypeScript strict + Pinia + Vue Router (frontend); FastAPI + SQLAlchemy 2.0 async + PostgreSQL + Alembic + `openai` SDK (backend).

---

## File Map

**Create:**
- `backend/app/models/chat_schemas.py`
- `backend/alembic/versions/061_add_dashboard_conversations.py`
- `backend/app/api/chats.py`
- `backend/tests/test_dashboard_chats.py`
- `frontend/src/types/chat.ts`
- `frontend/src/stores/chat.ts`
- `frontend/src/components/Chat/ChatListItem.vue`
- `frontend/src/components/Chat/ChatListPanel.vue`
- `frontend/src/components/Chat/ChatConversation.vue`
- `frontend/src/views/ChatsView.vue`

**Modify:**
- `backend/app/db/models.py` — append `DashboardConversation` and `DashboardMessage`
- `backend/app/main.py` — import and register `chats` router
- `frontend/src/services/api.ts` — add `chatApi` export
- `frontend/src/router/index.ts` — add `/chats` and `/chats/:id` routes
- `frontend/src/components/Layout/DashboardNav.vue` — route chat tab to `/chats`, update `activeTab`

---

### Task 1: Add SQLAlchemy Models

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Append the two model classes at the end of `backend/app/db/models.py`**

All required imports (`Boolean`, `Text`, `func`, `DateTime`, `String`, `ForeignKey`, `UUID`, `relationship`, `Mapped`, `mapped_column`, `uuid`, `datetime`) are already at the top of this file.

```python
class DashboardConversation(Base):
    __tablename__ = "dashboard_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Chat")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["DashboardMessage"]] = relationship(
        "DashboardMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class DashboardMessage(Base):
    __tablename__ = "dashboard_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dashboard_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["DashboardConversation"] = relationship(
        "DashboardConversation", back_populates="messages"
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(chat): add DashboardConversation and DashboardMessage SQLAlchemy models"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/061_add_dashboard_conversations.py`

- [ ] **Step 1: Create the migration file**

```python
"""add dashboard_conversations and dashboard_messages tables

Revision ID: 061
Revises: 060
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "061"
down_revision: str = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Chat"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_dashboard_conversations_user_id", "dashboard_conversations", ["user_id"]
    )

    op.create_table(
        "dashboard_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["dashboard_conversations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_dashboard_messages_conversation_id", "dashboard_messages", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_table("dashboard_messages")
    op.drop_table("dashboard_conversations")
```

- [ ] **Step 2: Run the migration**

```bash
cd backend && uv run alembic upgrade head
```

Expected output contains:
```
INFO  [alembic.runtime.migration] Running upgrade 060 -> 061, add dashboard_conversations and dashboard_messages tables
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/061_add_dashboard_conversations.py
git commit -m "feat(chat): add migration 061 for dashboard_conversations and dashboard_messages"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/models/chat_schemas.py`

- [ ] **Step 1: Create the schemas file**

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New Chat"


class ConversationUpdate(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str
    credential_id: str
    model: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/chat_schemas.py
git commit -m "feat(chat): add Pydantic schemas for dashboard chat"
```

---

### Task 4: Backend Router (CRUD + Streaming) + Register in main.py

**Files:**
- Create: `backend/app/api/chats.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/api/chats.py`**

```python
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.db.models import Credential, DashboardConversation, DashboardMessage, User
from app.db.session import async_session_maker
from app.models.chat_schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.services.encryption import decrypt_config

router = APIRouter()


async def _get_conversation_or_404(
    conversation_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> DashboardConversation:
    result = await db.execute(
        select(DashboardConversation).where(
            DashboardConversation.id == conversation_id,
            DashboardConversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """List all conversations for the current user, pinned first then newest."""
    result = await db.execute(
        select(DashboardConversation)
        .where(DashboardConversation.user_id == current_user.id)
        .order_by(
            DashboardConversation.is_pinned.desc(),
            DashboardConversation.updated_at.desc(),
        )
    )
    conversations = result.scalars().all()
    return ConversationListResponse(
        conversations=[ConversationResponse.model_validate(c) for c in conversations]
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Create a new conversation."""
    conversation = DashboardConversation(
        user_id=current_user.id,
        title=body.title or "New Chat",
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Get a conversation with all its messages."""
    result = await db.execute(
        select(DashboardConversation)
        .where(
            DashboardConversation.id == conversation_id,
            DashboardConversation.user_id == current_user.id,
        )
        .options(selectinload(DashboardConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    sorted_messages = sorted(conversation.messages, key=lambda m: m.created_at)
    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        is_pinned=conversation.is_pinned,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in sorted_messages],
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Rename a conversation and/or toggle its pin state."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    if body.title is not None:
        conversation.title = body.title
    if body.is_pinned is not None:
        conversation.is_pinned = body.is_pinned
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a conversation and all its messages."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    await db.delete(conversation)
    await db.commit()


async def _generate_chat_stream(
    conversation_id: uuid.UUID,
    api_key: str,
    base_url: str | None,
    model: str,
    history: list[dict[str, str]],
    user_content: str,
) -> AsyncGenerator[str, None]:
    """Stream an LLM reply, persisting user and assistant messages via a fresh DB session."""
    async with async_session_maker() as session:
        session.add(
            DashboardMessage(
                conversation_id=conversation_id,
                role="user",
                content=user_content,
            )
        )
        await session.commit()

    messages = history + [{"role": "user", "content": user_content}]
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    chunks: list[str] = []

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            if text:
                chunks.append(text)
                yield f"data: {json.dumps({'type': 'content', 'text': text})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
        return

    async with async_session_maker() as session:
        session.add(
            DashboardMessage(
                conversation_id=conversation_id,
                role="assistant",
                content="".join(chunks),
            )
        )
        await session.commit()

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/{conversation_id}/messages")
async def stream_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a user message and stream the assistant reply via SSE."""
    await _get_conversation_or_404(conversation_id, current_user.id, db)

    msg_result = await db.execute(
        select(DashboardMessage)
        .where(DashboardMessage.conversation_id == conversation_id)
        .order_by(DashboardMessage.created_at)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in msg_result.scalars().all()[-25:]
    ]

    cred_result = await db.execute(
        select(Credential).where(
            Credential.id == uuid.UUID(body.credential_id),
            Credential.user_id == current_user.id,
        )
    )
    credential = cred_result.scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    config = decrypt_config(credential.config)

    return StreamingResponse(
        _generate_chat_stream(
            conversation_id=conversation_id,
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url") or None,
            model=body.model,
            history=history,
            user_content=body.content,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: Register the router in `backend/app/main.py`**

Add `chats` to the import block at the top of `main.py`. The existing block is:

```python
from app.api import (
    agent_memory,
    ai_assistant,
    ...
    workflows,
)
```

Add `chats,` to that import list (alphabetically between `bigquery_oauth` and `config`):

```python
from app.api import (
    agent_memory,
    ai_assistant,
    analytics,
    auth,
    bigquery_oauth,
    chats,
    config,
    ...
)
```

Then add the router include after the `expressions` line (around line 175 of the original):

```python
app.include_router(chats.router, prefix="/api/chats", tags=["Chats"])
```

- [ ] **Step 3: Verify the app starts**

```bash
cd backend && uv run uvicorn app.main:app --port 10105 --reload &
sleep 3
curl -s http://localhost:10105/api/health | python3 -m json.tool
kill %1
```

Expected output:
```json
{
    "status": "healthy",
    "service": "heym-api",
    "version": "..."
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/chats.py backend/app/main.py
git commit -m "feat(chat): add chats API router with CRUD and SSE streaming"
```

---

### Task 5: Backend Tests

**Files:**
- Create: `backend/tests/test_dashboard_chats.py`

- [ ] **Step 1: Create the test file**

```python
import uuid
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.api.chats import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)
from app.db.models import DashboardConversation, DashboardMessage
from app.models.chat_schemas import ConversationCreate, ConversationUpdate


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_conversation(
    user_id: uuid.UUID,
    title: str = "Test Chat",
    is_pinned: bool = False,
) -> DashboardConversation:
    conv = DashboardConversation()
    conv.id = uuid.uuid4()
    conv.user_id = user_id
    conv.title = title
    conv.is_pinned = is_pinned
    conv.created_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)
    conv.messages = []
    return conv


def _make_db(scalars_result: list | None = None, scalar_one: object = None) -> AsyncMock:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    if scalars_result is not None:
        mock_result.scalars.return_value.all.return_value = scalars_result
    if scalar_one is not None:
        mock_result.scalar_one_or_none.return_value = scalar_one
    mock_db.execute.return_value = mock_result
    return mock_db


class TestListConversations(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_list_when_no_conversations(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalars_result=[])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertEqual(result.conversations, [])

    async def test_returns_conversations_for_user(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, title="My Chat")
        mock_db = _make_db(scalars_result=[conv])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertEqual(len(result.conversations), 1)
        self.assertEqual(result.conversations[0].title, "My Chat")

    async def test_pinned_conversations_appear_first(self) -> None:
        user = _make_user()
        pinned = _make_conversation(user.id, title="Pinned", is_pinned=True)
        unpinned = _make_conversation(user.id, title="Unpinned", is_pinned=False)
        # DB returns pinned first (query has ORDER BY is_pinned DESC)
        mock_db = _make_db(scalars_result=[pinned, unpinned])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertTrue(result.conversations[0].is_pinned)
        self.assertFalse(result.conversations[1].is_pinned)


class TestCreateConversation(unittest.IsolatedAsyncioTestCase):
    async def test_creates_with_given_title(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()

        added: list[DashboardConversation] = []
        mock_db.add.side_effect = lambda obj: added.append(obj)

        async def fake_refresh(obj: DashboardConversation) -> None:
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        result = await create_conversation(
            body=ConversationCreate(title="Hello"),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(result.title, "Hello")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    async def test_defaults_title_to_new_chat(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()

        added: list[DashboardConversation] = []
        mock_db.add.side_effect = lambda obj: added.append(obj)

        async def fake_refresh(obj: DashboardConversation) -> None:
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        await create_conversation(
            body=ConversationCreate(),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(added[0].title, "New Chat")


class TestGetConversation(unittest.IsolatedAsyncioTestCase):
    async def test_returns_conversation_with_messages(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        msg = DashboardMessage()
        msg.id = uuid.uuid4()
        msg.conversation_id = conv.id
        msg.role = "user"
        msg.content = "Hello"
        msg.created_at = datetime.now(timezone.utc)
        conv.messages = [msg]

        mock_db = _make_db(scalar_one=conv)

        result = await get_conversation(
            conversation_id=conv.id,
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(result.id, conv.id)
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].content, "Hello")

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await get_conversation(
                conversation_id=uuid.uuid4(),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestUpdateConversation(unittest.IsolatedAsyncioTestCase):
    async def test_renames_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, title="Old Title")
        mock_db = _make_db(scalar_one=conv)

        async def fake_refresh(obj: DashboardConversation) -> None:
            pass

        mock_db.refresh.side_effect = fake_refresh

        result = await update_conversation(
            conversation_id=conv.id,
            body=ConversationUpdate(title="New Title"),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(conv.title, "New Title")
        self.assertEqual(result.title, "New Title")

    async def test_pins_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, is_pinned=False)
        mock_db = _make_db(scalar_one=conv)
        mock_db.refresh.side_effect = AsyncMock()

        await update_conversation(
            conversation_id=conv.id,
            body=ConversationUpdate(is_pinned=True),
            current_user=user,
            db=mock_db,
        )

        self.assertTrue(conv.is_pinned)

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await update_conversation(
                conversation_id=uuid.uuid4(),
                body=ConversationUpdate(title="x"),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestDeleteConversation(unittest.IsolatedAsyncioTestCase):
    async def test_deletes_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        mock_db = _make_db(scalar_one=conv)

        await delete_conversation(
            conversation_id=conv.id,
            current_user=user,
            db=mock_db,
        )

        mock_db.delete.assert_awaited_once_with(conv)
        mock_db.commit.assert_awaited()

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await delete_conversation(
                conversation_id=uuid.uuid4(),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)
```

Add this class at the end of the file, after `TestDeleteConversation`:

```python
class TestStreamMessageAuth(unittest.IsolatedAsyncioTestCase):
    async def test_raises_404_when_conversation_not_found(self) -> None:
        from app.api.chats import stream_message
        from app.models.chat_schemas import MessageCreate as MC

        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await stream_message(
                conversation_id=uuid.uuid4(),
                body=MC(content="hello", credential_id=str(uuid.uuid4()), model="gpt-4o"),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)
```

- [ ] **Step 2: Run the tests and verify they pass**

```bash
cd backend && uv run pytest tests/test_dashboard_chats.py -v
```

Expected output — all tests pass:
```
PASSED tests/test_dashboard_chats.py::TestListConversations::test_returns_empty_list_when_no_conversations
PASSED tests/test_dashboard_chats.py::TestListConversations::test_returns_conversations_for_user
PASSED tests/test_dashboard_chats.py::TestListConversations::test_pinned_conversations_appear_first
PASSED tests/test_dashboard_chats.py::TestCreateConversation::test_creates_with_given_title
PASSED tests/test_dashboard_chats.py::TestCreateConversation::test_defaults_title_to_new_chat
PASSED tests/test_dashboard_chats.py::TestGetConversation::test_returns_conversation_with_messages
PASSED tests/test_dashboard_chats.py::TestGetConversation::test_raises_404_for_wrong_user
PASSED tests/test_dashboard_chats.py::TestUpdateConversation::test_renames_conversation
PASSED tests/test_dashboard_chats.py::TestUpdateConversation::test_pins_conversation
PASSED tests/test_dashboard_chats.py::TestUpdateConversation::test_raises_404_for_wrong_user
PASSED tests/test_dashboard_chats.py::TestDeleteConversation::test_deletes_conversation
PASSED tests/test_dashboard_chats.py::TestDeleteConversation::test_raises_404_for_wrong_user
PASSED tests/test_dashboard_chats.py::TestStreamMessageAuth::test_raises_404_when_conversation_not_found
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_dashboard_chats.py
git commit -m "feat(chat): add backend tests for dashboard chat CRUD"
```

---

### Task 6: Frontend TypeScript Types

**Files:**
- Create: `frontend/src/types/chat.ts`

- [ ] **Step 1: Create the types file**

```typescript
export interface DashboardConversation {
  id: string;
  title: string;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationListResponse {
  conversations: DashboardConversation[];
}

export interface ConversationDetailResponse extends DashboardConversation {
  messages: DashboardMessage[];
}

export interface ConversationUpdate {
  title?: string;
  is_pinned?: boolean;
}

export interface MessageCreate {
  content: string;
  credential_id: string;
  model: string;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/chat.ts
git commit -m "feat(chat): add TypeScript types for dashboard chat"
```

---

### Task 7: Frontend chatApi Service

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add the import for chat types at the top of `frontend/src/services/api.ts`**

The existing import block at the top of `api.ts` already imports from various type files. Add this import alongside the others:

```typescript
import type {
  ConversationDetailResponse,
  ConversationListResponse,
  ConversationUpdate,
  DashboardConversation,
  MessageCreate,
} from "@/types/chat";
```

- [ ] **Step 2: Add `chatApi` export before the `export default api;` line at the end of `frontend/src/services/api.ts`**

```typescript
export const chatApi = {
  list: (): Promise<ConversationListResponse> =>
    api.get<ConversationListResponse>("/api/chats").then((r) => r.data),

  create: (title?: string): Promise<DashboardConversation> =>
    api.post<DashboardConversation>("/api/chats", { title }).then((r) => r.data),

  get: (id: string): Promise<ConversationDetailResponse> =>
    api.get<ConversationDetailResponse>(`/api/chats/${id}`).then((r) => r.data),

  update: (id: string, data: ConversationUpdate): Promise<DashboardConversation> =>
    api.put<DashboardConversation>(`/api/chats/${id}`, data).then((r) => r.data),

  delete: (id: string): Promise<void> =>
    api.delete(`/api/chats/${id}`).then(() => {}),

  streamMessage: (
    conversationId: string,
    payload: MessageCreate,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: Error) => void,
    signal?: AbortSignal,
  ): void => {
    const API_URL = import.meta.env.VITE_API_URL || "";
    fetch(`${API_URL}/api/chats/${conversationId}/messages`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...heymClientHeaders },
      body: JSON.stringify(payload),
      signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          onError(new Error(`HTTP ${response.status}`));
          return;
        }
        const reader = response.body?.getReader();
        if (!reader) {
          onError(new Error("No response body"));
          return;
        }
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            if (!part.startsWith("data: ")) continue;
            const data = JSON.parse(part.slice(6)) as {
              type: string;
              text?: string;
            };
            if (data.type === "content" && data.text) onChunk(data.text);
            else if (data.type === "done") onDone();
            else if (data.type === "error")
              onError(new Error(data.text ?? "Stream error"));
          }
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        onError(err instanceof Error ? err : new Error("Stream failed"));
      });
  },
};
```

- [ ] **Step 3: Run typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors related to `chatApi` or `chat.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/types/chat.ts
git commit -m "feat(chat): add chatApi service with streaming support"
```

---

### Task 8: Pinia Chat Store

**Files:**
- Create: `frontend/src/stores/chat.ts`

- [ ] **Step 1: Create the store file**

```typescript
import { ref } from "vue";
import { defineStore } from "pinia";
import { useRouter } from "vue-router";

import { useToast } from "@/composables/useToast";
import { chatApi } from "@/services/api";
import type { DashboardConversation, DashboardMessage, MessageCreate } from "@/types/chat";

const SIDEBAR_KEY = "heym-chat-sidebar-open";

function readSidebarOpen(): boolean {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_KEY);
    return raw === null ? true : raw === "true";
  } catch {
    return true;
  }
}

export const useChatStore = defineStore("chat", () => {
  const router = useRouter();
  const { showToast } = useToast();

  const conversations = ref<DashboardConversation[]>([]);
  const activeId = ref<string | null>(null);
  const messages = ref<DashboardMessage[]>([]);
  const sidebarOpen = ref<boolean>(readSidebarOpen());
  const isLoadingConversations = ref(false);
  const isStreaming = ref(false);

  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value;
    try {
      window.localStorage.setItem(SIDEBAR_KEY, String(sidebarOpen.value));
    } catch {
      // ignore storage errors
    }
  }

  async function fetchConversations(): Promise<void> {
    isLoadingConversations.value = true;
    try {
      const response = await chatApi.list();
      conversations.value = response.conversations;
    } catch {
      showToast("Failed to load conversations", "error");
    } finally {
      isLoadingConversations.value = false;
    }
  }

  async function createConversation(): Promise<void> {
    try {
      const conv = await chatApi.create();
      conversations.value.unshift(conv);
      await router.push(`/chats/${conv.id}`);
    } catch {
      showToast("Failed to create conversation", "error");
    }
  }

  async function loadConversation(id: string): Promise<void> {
    activeId.value = id;
    try {
      const detail = await chatApi.get(id);
      messages.value = detail.messages;
      const idx = conversations.value.findIndex((c) => c.id === id);
      if (idx >= 0) {
        conversations.value[idx] = {
          id: detail.id,
          title: detail.title,
          is_pinned: detail.is_pinned,
          created_at: detail.created_at,
          updated_at: detail.updated_at,
        };
      }
    } catch (err: unknown) {
      const status =
        err && typeof err === "object" && "response" in err
          ? (err as { response: { status: number } }).response.status
          : 0;
      if (status === 404 || status === 403) {
        showToast("Conversation not found", "error");
        await router.push("/chats");
        return;
      }
      showToast("Failed to load conversation", "error");
    }
  }

  async function renameConversation(id: string, title: string): Promise<void> {
    try {
      const updated = await chatApi.update(id, { title });
      const idx = conversations.value.findIndex((c) => c.id === id);
      if (idx >= 0) conversations.value[idx] = updated;
    } catch {
      showToast("Failed to rename", "error");
    }
  }

  async function togglePin(id: string): Promise<void> {
    const conv = conversations.value.find((c) => c.id === id);
    if (!conv) return;
    try {
      const updated = await chatApi.update(id, { is_pinned: !conv.is_pinned });
      const idx = conversations.value.findIndex((c) => c.id === id);
      if (idx >= 0) conversations.value[idx] = updated;
      conversations.value.sort((a, b) => {
        if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
    } catch {
      showToast("Failed to update pin", "error");
    }
  }

  async function deleteConversation(id: string): Promise<void> {
    try {
      await chatApi.delete(id);
      conversations.value = conversations.value.filter((c) => c.id !== id);
      if (activeId.value === id) {
        activeId.value = null;
        messages.value = [];
        await router.push("/chats");
      }
    } catch {
      showToast("Failed to delete conversation", "error");
    }
  }

  async function sendMessage(
    id: string,
    content: string,
    credentialId: string,
    model: string,
  ): Promise<void> {
    if (isStreaming.value) return;

    const userMsg: DashboardMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    messages.value.push(userMsg);

    const assistantMsg: DashboardMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };
    messages.value.push(assistantMsg);
    isStreaming.value = true;

    const payload: MessageCreate = { content, credential_id: credentialId, model };

    chatApi.streamMessage(
      id,
      payload,
      (text) => {
        assistantMsg.content += text;
      },
      () => {
        isStreaming.value = false;
      },
      (err) => {
        assistantMsg.content = `Error: ${err.message}`;
        isStreaming.value = false;
      },
    );
  }

  return {
    conversations,
    activeId,
    messages,
    sidebarOpen,
    isLoadingConversations,
    isStreaming,
    toggleSidebar,
    fetchConversations,
    createConversation,
    loadConversation,
    renameConversation,
    togglePin,
    deleteConversation,
    sendMessage,
  };
});
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/chat.ts
git commit -m "feat(chat): add Pinia chat store"
```

---

### Task 9: Router + DashboardNav Updates

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/Layout/DashboardNav.vue`

- [ ] **Step 1: Add routes to `frontend/src/router/index.ts`**

Add the two chat routes inside the `routes` array, after the `/evals` route:

```typescript
{
  path: "/chats",
  name: "chats",
  component: () => import("@/views/ChatsView.vue"),
  meta: { requiresAuth: true },
},
{
  path: "/chats/:id",
  name: "chats-detail",
  component: () => import("@/views/ChatsView.vue"),
  meta: { requiresAuth: true },
},
```

- [ ] **Step 2: Update `frontend/src/components/Layout/DashboardNav.vue` — three changes**

**Change 1:** Update `activeTab` computed to recognise `/chats` as the chat tab. In the existing `activeTab` computed, add a check for the chats path before the `tabParam` checks:

Replace:
```typescript
const activeTab = computed(() => {
  if (route.path === "/evals") return "evals";
  const tabParam = route.query.tab as string;
```

With:
```typescript
const activeTab = computed(() => {
  if (route.path === "/evals") return "evals";
  if (route.path.startsWith("/chats")) return "chat";
  const tabParam = route.query.tab as string;
```

**Change 2:** Update `getTabHref` to return `/chats` for the chat tab. Replace:

```typescript
function getTabHref(tabId: (typeof tabs)[number]["id"]): string {
  if (tabId === "evals") return "/evals";
  if (tabId === "workflows") return "/";
  return `/?tab=${tabId}`;
}
```

With:

```typescript
function getTabHref(tabId: (typeof tabs)[number]["id"]): string {
  if (tabId === "evals") return "/evals";
  if (tabId === "workflows") return "/";
  if (tabId === "chat") return "/chats";
  return `/?tab=${tabId}`;
}
```

**Change 3:** Update `goToTab` to navigate to `/chats` for the chat tab. Add a case before the final `router.push({ path: "/", query: { tab: tabId } })`:

Replace:
```typescript
  if (tabId === "evals") {
    router.push("/evals");
    return;
  }
  if (tabId === "workflows") {
    router.push("/");
    return;
  }
  router.push({ path: "/", query: { tab: tabId } });
```

With:
```typescript
  if (tabId === "evals") {
    router.push("/evals");
    return;
  }
  if (tabId === "workflows") {
    router.push("/");
    return;
  }
  if (tabId === "chat") {
    router.push("/chats");
    return;
  }
  router.push({ path: "/", query: { tab: tabId } });
```

- [ ] **Step 3: Run typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router/index.ts frontend/src/components/Layout/DashboardNav.vue
git commit -m "feat(chat): add /chats routes and update DashboardNav chat tab"
```

---

### Task 10: ChatListItem Component

**Files:**
- Create: `frontend/src/components/Chat/ChatListItem.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { Check, PencilLine, Pin, PinOff, Trash2, X } from "lucide-vue-next";

import { useChatStore } from "@/stores/chat";
import type { DashboardConversation } from "@/types/chat";

interface Props {
  conversation: DashboardConversation;
  isActive: boolean;
}

const props = defineProps<Props>();
const chatStore = useChatStore();
const router = useRouter();

const isRenaming = ref(false);
const renameValue = ref("");
const showDeleteConfirm = ref(false);

function startRename(): void {
  renameValue.value = props.conversation.title;
  isRenaming.value = true;
}

async function commitRename(): Promise<void> {
  isRenaming.value = false;
  const trimmed = renameValue.value.trim();
  if (trimmed && trimmed !== props.conversation.title) {
    await chatStore.renameConversation(props.conversation.id, trimmed);
  }
}

function cancelRename(): void {
  isRenaming.value = false;
}

async function handleDelete(): Promise<void> {
  showDeleteConfirm.value = false;
  await chatStore.deleteConversation(props.conversation.id);
}

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
</script>

<template>
  <div
    class="group relative flex items-start gap-2 rounded-md px-3 py-2 cursor-pointer hover:bg-muted/50 transition-colors"
    :class="{ 'bg-muted border-l-2 border-primary': isActive }"
    @click="router.push(`/chats/${conversation.id}`)"
  >
    <div class="flex-1 min-w-0">
      <template v-if="isRenaming">
        <input
          v-model="renameValue"
          class="w-full bg-background border border-border rounded px-1 py-0.5 text-sm text-foreground focus:outline-none"
          autofocus
          @keydown.enter.prevent="commitRename"
          @keydown.escape.prevent="cancelRename"
          @blur="commitRename"
          @click.stop
        />
      </template>
      <template v-else>
        <p class="text-sm font-medium text-foreground truncate">{{ conversation.title }}</p>
        <p class="text-xs text-muted-foreground">{{ formatRelative(conversation.updated_at) }}</p>
      </template>
    </div>

    <div
      class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
      @click.stop
    >
      <button
        class="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
        :title="conversation.is_pinned ? 'Unpin' : 'Pin to top'"
        @click="chatStore.togglePin(conversation.id)"
      >
        <PinOff v-if="conversation.is_pinned" class="h-3 w-3" />
        <Pin v-else class="h-3 w-3" />
      </button>
      <button
        class="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
        title="Rename"
        @click="startRename"
      >
        <PencilLine class="h-3 w-3" />
      </button>
      <button
        class="p-0.5 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive"
        title="Delete"
        @click="showDeleteConfirm = true"
      >
        <Trash2 class="h-3 w-3" />
      </button>
    </div>

    <div
      v-if="showDeleteConfirm"
      class="absolute right-0 top-8 z-10 bg-background border border-border rounded-md shadow-lg p-3 w-44"
      @click.stop
    >
      <p class="text-xs text-foreground mb-2">Delete this chat?</p>
      <div class="flex gap-2">
        <button
          class="flex items-center gap-1 text-xs bg-destructive text-destructive-foreground rounded px-2 py-1 hover:opacity-90"
          @click="handleDelete"
        >
          <Check class="h-3 w-3" /> Yes
        </button>
        <button
          class="flex items-center gap-1 text-xs bg-muted text-muted-foreground rounded px-2 py-1 hover:opacity-90"
          @click="showDeleteConfirm = false"
        >
          <X class="h-3 w-3" /> No
        </button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && bun run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatListItem.vue
git commit -m "feat(chat): add ChatListItem component"
```

---

### Task 11: ChatListPanel Component

**Files:**
- Create: `frontend/src/components/Chat/ChatListPanel.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { computed } from "vue";
import { ChevronLeft, ChevronRight, MessageSquarePlus } from "lucide-vue-next";

import ChatListItem from "@/components/Chat/ChatListItem.vue";
import Button from "@/components/ui/Button.vue";
import { useChatStore } from "@/stores/chat";

const chatStore = useChatStore();

const pinned = computed(() => chatStore.conversations.filter((c) => c.is_pinned));
const unpinned = computed(() => chatStore.conversations.filter((c) => !c.is_pinned));
</script>

<template>
  <div class="flex h-full shrink-0">
    <!-- Collapsed toggle -->
    <div v-if="!chatStore.sidebarOpen" class="flex flex-col items-center pt-3 px-1 border-r border-border">
      <button
        class="p-1 rounded hover:bg-muted text-muted-foreground"
        title="Open chat list"
        @click="chatStore.toggleSidebar()"
      >
        <ChevronRight class="h-4 w-4" />
      </button>
    </div>

    <!-- Expanded sidebar -->
    <div v-else class="flex flex-col w-56 border-r border-border bg-background h-full">
      <!-- Header -->
      <div class="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <span class="text-sm font-semibold text-foreground">Chats</span>
        <div class="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            class="h-6 w-6"
            title="New chat"
            @click="chatStore.createConversation()"
          >
            <MessageSquarePlus class="h-4 w-4" />
          </Button>
          <button
            class="p-1 rounded hover:bg-muted text-muted-foreground"
            title="Close"
            @click="chatStore.toggleSidebar()"
          >
            <ChevronLeft class="h-4 w-4" />
          </button>
        </div>
      </div>

      <!-- Scrollable list -->
      <div class="flex-1 overflow-y-auto py-1">
        <template v-if="pinned.length > 0">
          <p class="px-3 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            📌 Pinned
          </p>
          <ChatListItem
            v-for="conv in pinned"
            :key="conv.id"
            :conversation="conv"
            :is-active="chatStore.activeId === conv.id"
          />
        </template>

        <template v-if="unpinned.length > 0">
          <p
            v-if="pinned.length > 0"
            class="px-3 py-1 mt-1 text-xs font-medium text-muted-foreground uppercase tracking-wider"
          >
            Recent
          </p>
          <ChatListItem
            v-for="conv in unpinned"
            :key="conv.id"
            :conversation="conv"
            :is-active="chatStore.activeId === conv.id"
          />
        </template>

        <div
          v-if="chatStore.conversations.length === 0 && !chatStore.isLoadingConversations"
          class="px-3 py-6 text-center"
        >
          <p class="text-sm text-muted-foreground">No chats yet</p>
          <Button variant="ghost" size="sm" class="mt-2" @click="chatStore.createConversation()">
            Start a chat
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && bun run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatListPanel.vue
git commit -m "feat(chat): add ChatListPanel component"
```

---

### Task 12: ChatConversation Component

**Files:**
- Create: `frontend/src/components/Chat/ChatConversation.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { PencilLine, Send } from "lucide-vue-next";

import Button from "@/components/ui/Button.vue";
import { credentialsApi } from "@/services/api";
import { useChatStore } from "@/stores/chat";
import type { CredentialListItem, LLMModel } from "@/types/credential";

const chatStore = useChatStore();

const input = ref("");
const messagesEl = ref<HTMLElement | null>(null);
const isRenaming = ref(false);
const renameValue = ref("");

const credentials = ref<CredentialListItem[]>([]);
const models = ref<LLMModel[]>([]);
const selectedCredentialId = ref("");
const selectedModel = ref("");

const activeConversation = computed(() =>
  chatStore.conversations.find((c) => c.id === chatStore.activeId),
);

async function loadCredentials(): Promise<void> {
  try {
    const list = await credentialsApi.listLLM();
    credentials.value = list;
    if (list.length > 0 && !selectedCredentialId.value) {
      selectedCredentialId.value = list[0].id;
      await loadModels();
    }
  } catch {
    // ignore
  }
}

async function loadModels(): Promise<void> {
  if (!selectedCredentialId.value) return;
  try {
    const list = await credentialsApi.getModels(selectedCredentialId.value);
    models.value = list;
    if (list.length > 0) selectedModel.value = list[0].id;
  } catch {
    // ignore
  }
}

async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text || !chatStore.activeId || !selectedCredentialId.value || !selectedModel.value) return;
  input.value = "";
  await chatStore.sendMessage(chatStore.activeId, text, selectedCredentialId.value, selectedModel.value);
  await nextTick();
  scrollToBottom();
}

function scrollToBottom(): void {
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

function renderMarkdown(content: string): string {
  return DOMPurify.sanitize(marked.parse(content) as string);
}

function startRename(): void {
  if (!activeConversation.value) return;
  renameValue.value = activeConversation.value.title;
  isRenaming.value = true;
}

async function commitRename(): Promise<void> {
  isRenaming.value = false;
  if (!chatStore.activeId || !renameValue.value.trim()) return;
  await chatStore.renameConversation(chatStore.activeId, renameValue.value.trim());
}

watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick();
    scrollToBottom();
  },
);

onMounted(loadCredentials);
</script>

<template>
  <div class="flex flex-col h-full flex-1 min-w-0">
    <!-- Empty state -->
    <div v-if="!chatStore.activeId" class="flex flex-1 items-center justify-center">
      <div class="text-center">
        <p class="text-muted-foreground">Select a chat or create a new one</p>
        <Button variant="outline" class="mt-3" @click="chatStore.createConversation()">
          New Chat
        </Button>
      </div>
    </div>

    <template v-else>
      <!-- Header -->
      <div class="flex items-center gap-2 px-4 py-2 border-b border-border shrink-0">
        <template v-if="isRenaming">
          <input
            v-model="renameValue"
            class="flex-1 bg-background border border-border rounded px-2 py-1 text-sm font-semibold focus:outline-none"
            autofocus
            @keydown.enter.prevent="commitRename"
            @keydown.escape.prevent="isRenaming = false"
            @blur="commitRename"
          />
        </template>
        <template v-else>
          <h1 class="text-sm font-semibold flex-1 truncate">
            {{ activeConversation?.title ?? "Chat" }}
          </h1>
          <button
            class="p-1 rounded hover:bg-muted text-muted-foreground"
            title="Rename"
            @click="startRename"
          >
            <PencilLine class="h-3.5 w-3.5" />
          </button>
        </template>
      </div>

      <!-- Messages -->
      <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <div
          v-for="msg in chatStore.messages"
          :key="msg.id"
          class="flex"
          :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[75%] rounded-lg px-3 py-2 text-sm"
            :class="
              msg.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground'
            "
          >
            <div
              v-if="msg.role === 'assistant'"
              class="prose prose-sm dark:prose-invert max-w-none"
              v-html="renderMarkdown(msg.content)"
            />
            <span v-else>{{ msg.content }}</span>
          </div>
        </div>
      </div>

      <!-- Input area -->
      <div class="border-t border-border px-4 py-3 space-y-2 shrink-0">
        <div class="flex items-center gap-2">
          <select
            v-model="selectedCredentialId"
            class="text-xs border border-border rounded px-2 py-1 bg-background text-foreground"
            @change="loadModels"
          >
            <option v-for="cred in credentials" :key="cred.id" :value="cred.id">
              {{ cred.name }}
            </option>
          </select>
          <select
            v-model="selectedModel"
            class="text-xs border border-border rounded px-2 py-1 bg-background text-foreground"
          >
            <option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option>
          </select>
        </div>
        <div class="flex items-end gap-2">
          <textarea
            v-model="input"
            rows="2"
            placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
            class="flex-1 resize-none border border-border rounded-md px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            @keydown.enter.exact.prevent="send"
            @keydown.enter.shift.exact.prevent="input += '\n'"
          />
          <Button
            size="icon"
            :disabled="!input.trim() || chatStore.isStreaming"
            @click="send"
          >
            <Send class="h-4 w-4" />
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && bun run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatConversation.vue
git commit -m "feat(chat): add ChatConversation component with streaming and markdown"
```

---

### Task 13: ChatsView

**Files:**
- Create: `frontend/src/views/ChatsView.vue`

- [ ] **Step 1: Create the view**

```vue
<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import ChatConversation from "@/components/Chat/ChatConversation.vue";
import ChatListPanel from "@/components/Chat/ChatListPanel.vue";
import { useChatStore } from "@/stores/chat";

const route = useRoute();
const chatStore = useChatStore();

async function init(): Promise<void> {
  const id = route.params.id as string | undefined;
  const tasks: Promise<void>[] = [chatStore.fetchConversations()];
  if (id) tasks.push(chatStore.loadConversation(id));
  await Promise.all(tasks);
}

onMounted(init);

watch(
  () => route.params.id,
  (newId) => {
    if (newId && typeof newId === "string") {
      chatStore.loadConversation(newId);
    } else {
      chatStore.activeId = null;
    }
  },
);
</script>

<template>
  <div class="flex h-screen bg-background">
    <ChatListPanel />
    <ChatConversation />
  </div>
</template>
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && bun run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ChatsView.vue
git commit -m "feat(chat): add ChatsView"
```

---

### Task 14: Full Check

**Files:** none

- [ ] **Step 1: Run the full check script from the repo root**

```bash
cd /path/to/heymrun && ./check.sh
```

Expected: lint passes, typecheck passes, all backend tests pass (including `test_dashboard_chats.py`).

- [ ] **Step 2: If ruff auto-formatted any files, stage and commit them**

```bash
git add backend/
git commit -m "style: ruff format backend/app/api/chats.py and related files"
```

- [ ] **Step 3: Smoke-test the UI manually**

1. Start services: `./run.sh`
2. Open `http://localhost:4017`
3. Click the 💬 Chat tab in the left nav — should navigate to `/chats`
4. Click "New Chat" — URL changes to `/chats/:id`, new conversation appears in sidebar
5. Select a credential and model, type a message, press Enter — assistant reply streams in
6. Hover the conversation in the sidebar — rename (pencil), pin, delete icons appear
7. Click the pin icon — conversation moves to "📌 Pinned" section
8. Click the chevron — sidebar collapses; click again to expand
9. Reload the page on `/chats/:id` — conversation and messages reload from DB
10. Delete the conversation — navigates to `/chats`, conversation removed from list
