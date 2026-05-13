# Chat Background Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four features to the `/chats` screen: per-conversation background task processing with reconnectable SSE, running/unread indicators in the sidebar, drag-to-import file attachment, and a persistent per-user quick-prompt list shown in the empty-chat state.

**Architecture:** The existing `POST /{id}/messages` streaming endpoint is replaced by a fire-and-forget model: the endpoint saves the user message, marks `is_running=True`, starts an `asyncio.create_task`, and returns `202`. A new `GET /{id}/stream` SSE endpoint lets the frontend subscribe to (or re-subscribe to) the in-flight task queue. On completion the task saves the assistant message to DB and sets `has_unread=True` if no subscriber is watching. Quick prompts are stored one-row-per-user in a new `dashboard_chat_quick_prompts` table.

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 async / Alembic / Vue 3 + TypeScript strict / Pinia

---

## File Map

### New files
| File | Purpose |
|------|---------|
| `backend/alembic/versions/064_chat_background_and_prompts.py` | DB migration |
| `backend/app/services/chat_task_registry.py` | In-memory asyncio.Queue registry |
| `backend/tests/test_chat_background_task.py` | Tests for POST /messages + GET /stream |
| `backend/tests/test_chat_quick_prompts.py` | Tests for GET/PUT /quick-prompts |
| `frontend/src/composables/useQuickPrompts.ts` | Quick-prompt load/save/defaults |

### Modified files
| File | Change |
|------|--------|
| `backend/app/db/models.py` | Add `is_running`, `has_unread` to `DashboardConversation`; add `DashboardChatQuickPrompts` model |
| `backend/app/models/chat_schemas.py` | Add `is_running`, `has_unread` to `ConversationResponse`; add `QuickPromptsResponse`, `QuickPromptsUpdate` |
| `backend/app/api/chats.py` | Refactor `stream_message` → 202; add `GET /stream`, `PATCH /read`, `GET /quick-prompts`, `PUT /quick-prompts` |
| `backend/app/main.py` | Startup cleanup: reset stale `is_running` rows |
| `frontend/src/types/chat.ts` | Add `is_running`, `has_unread` to `Conversation` |
| `frontend/src/services/api.ts` | Add `sendMessage`, `subscribeStream`, `markConversationRead`, `getQuickPrompts`, `saveQuickPrompts` |
| `frontend/src/stores/chat.ts` | Refactor `sendMessage`; add `markConversationRead`, `loadQuickPrompts`, `saveQuickPrompts`, `quickPrompts` |
| `frontend/src/components/Chat/ChatListItem.vue` | Add running bar + unread dot |
| `frontend/src/components/Chat/ChatConversation.vue` | Add drag-to-import overlay + quick-prompt empty state |

---

## Task 1: DB Migration

**Files:**
- Create: `backend/alembic/versions/064_chat_background_and_prompts.py`

- [ ] **Step 1: Create the migration file**

```python
# backend/alembic/versions/064_chat_background_and_prompts.py
"""add is_running, has_unread to conversations and quick_prompts table

Revision ID: 064
Revises: 063
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "064"
down_revision: str = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dashboard_conversations",
        sa.Column("is_running", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "dashboard_conversations",
        sa.Column("has_unread", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "dashboard_chat_quick_prompts",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("prompts", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="'[]'"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("dashboard_chat_quick_prompts")
    op.drop_column("dashboard_conversations", "has_unread")
    op.drop_column("dashboard_conversations", "is_running")
```

- [ ] **Step 2: Run the migration**

```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade 063 -> 064, add is_running, has_unread ...`

---

## Task 2: DB Models + Pydantic Schemas

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/models/chat_schemas.py`

- [ ] **Step 1: Add columns to DashboardConversation and new model**

In `backend/app/db/models.py`, find the `DashboardConversation` class and add two columns after `is_pinned`:

```python
# add after: is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
has_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Then add the new model at the end of the file (after `DashboardMessage`):

```python
class DashboardChatQuickPrompts(Base):
    __tablename__ = "dashboard_chat_quick_prompts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    prompts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

Note: `JSON` is already imported as `from sqlalchemy.dialects.postgresql import JSON, UUID` in models.py.

- [ ] **Step 2: Update Pydantic schemas**

Replace the `ConversationResponse` class in `backend/app/models/chat_schemas.py` and add new classes:

```python
class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    is_running: bool
    has_unread: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    is_running: bool
    has_unread: bool
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class QuickPromptsResponse(BaseModel):
    prompts: list[str]


class QuickPromptsUpdate(BaseModel):
    prompts: list[str]
```

Also update `MessageCreate` to add `SendMessageResponse`:

```python
class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
```

- [ ] **Step 3: Verify typecheck passes**

```bash
cd backend && uv run ruff check app/db/models.py app/models/chat_schemas.py
```

Expected: no errors.

---

## Task 3: Chat Task Registry

**Files:**
- Create: `backend/app/services/chat_task_registry.py`

- [ ] **Step 1: Write the registry module**

```python
# backend/app/services/chat_task_registry.py
from __future__ import annotations

import asyncio

_queues: dict[str, asyncio.Queue] = {}
_subscriber_counts: dict[str, int] = {}


def create_queue(conv_id: str) -> asyncio.Queue:
    """Create a new queue for conv_id, replacing any existing one."""
    q: asyncio.Queue = asyncio.Queue()
    _queues[conv_id] = q
    _subscriber_counts[conv_id] = 0
    return q


def get_queue(conv_id: str) -> asyncio.Queue | None:
    """Return the live queue for conv_id, or None if not present."""
    return _queues.get(conv_id)


def remove_queue(conv_id: str) -> None:
    """Remove queue and subscriber count for conv_id."""
    _queues.pop(conv_id, None)
    _subscriber_counts.pop(conv_id, None)


def increment_subscribers(conv_id: str) -> None:
    """Record that a new SSE client is reading from conv_id's queue."""
    _subscriber_counts[conv_id] = _subscriber_counts.get(conv_id, 0) + 1


def decrement_subscribers(conv_id: str) -> int:
    """Record that an SSE client disconnected. Returns remaining subscriber count."""
    current = _subscriber_counts.get(conv_id, 0)
    remaining = max(0, current - 1)
    _subscriber_counts[conv_id] = remaining
    return remaining


def subscriber_count(conv_id: str) -> int:
    """Return number of active SSE subscribers for conv_id."""
    return _subscriber_counts.get(conv_id, 0)
```

- [ ] **Step 2: Lint check**

```bash
cd backend && uv run ruff check app/services/chat_task_registry.py
```

Expected: no errors.

---

## Task 4: Backend — Refactor POST /messages + Add GET /stream + PATCH /read

**Files:**
- Modify: `backend/app/api/chats.py`

This task replaces the `stream_message` endpoint body and adds two new endpoints.

- [ ] **Step 1: Add new imports to chats.py**

At the top of `backend/app/api/chats.py`, add to the existing imports:

```python
import asyncio
import json
import uuid
from threading import Event

# add to the existing fastapi imports:
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

# add to existing app imports:
from app.db.models import (
    CredentialType,
    DashboardConversation,
    DashboardChatQuickPrompts,
    DashboardMessage,
    User,
)
from app.db.session import async_session_maker
from app.models.chat_schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationTitleGenerate,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    QuickPromptsResponse,
    QuickPromptsUpdate,
    SendMessageResponse,
)
from app.services import chat_task_registry as registry
```

Note: `chats.py` already imports most of these — only add the ones missing. Specifically these are new: `asyncio`, `Response`, `DashboardChatQuickPrompts`, `async_session_maker`, `QuickPromptsResponse`, `QuickPromptsUpdate`, `SendMessageResponse`, `chat_task_registry`.

- [ ] **Step 2: Add the process_chat background coroutine**

Add this function to `chats.py` BEFORE the `stream_message` endpoint (can go after `_fallback_title_from_content`):

```python
async def _process_chat(
    conv_id: uuid.UUID,
    user_id: uuid.UUID,
    client: object,
    model: str,
    provider: str,
    system_prompt: str,
    messages: list[dict],
    trace_context: object,
    public_base_url: str,
    attachment: "FileAttachment | None",
    credential: object,
    should_generate_title: bool,
    first_user_content: str,
) -> None:
    """Background task: stream LLM response into queue, save to DB, update flags."""
    conv_id_str = str(conv_id)
    queue = registry.get_queue(conv_id_str)
    if queue is None:
        return

    cancel_event = Event()
    assistant_chunks: list[str] = []
    workflow_context_markers: list[str] = []
    workflow_note_ids: set[str] = set()

    async with async_session_maker() as db:
        try:
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                await queue.put(json.dumps({"type": "error", "text": "User not found"}))
                await queue.put(None)
                return

            async for chunk in stream_dashboard_chat(
                client,
                model,
                system_prompt,
                messages,
                db,
                user,
                provider,
                public_base_url,
                trace_context,
                cancel_event,
                attachment,
                credential,
            ):
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                    except json.JSONDecodeError:
                        payload = {}
                    if payload.get("type") == "content":
                        assistant_chunks.append(str(payload.get("text") or ""))
                    elif payload.get("type") == "workflow_created":
                        w_id = str(payload.get("workflow_id") or "").strip()
                        w_name = str(payload.get("workflow_name") or "").strip()
                        if w_id and w_id not in workflow_note_ids:
                            workflow_note_ids.add(w_id)
                            workflow_context_markers.append(
                                _build_hidden_workflow_context_marker(w_id, w_name or "Workflow")
                            )
                await queue.put(chunk)

            assistant_content = "".join(assistant_chunks)
            for marker in workflow_context_markers:
                if marker and marker not in assistant_content:
                    assistant_content += marker

            if assistant_content:
                db.add(DashboardMessage(
                    conversation_id=conv_id,
                    role="assistant",
                    content=assistant_content,
                ))

            conv_result = await db.execute(
                select(DashboardConversation).where(DashboardConversation.id == conv_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv is not None:
                conv.is_running = False
                conv.has_unread = registry.subscriber_count(conv_id_str) == 0
                if should_generate_title and conv.title == DEFAULT_CONVERSATION_TITLE:
                    conv.title = _fallback_title_from_content(first_user_content)
                    await queue.put(
                        f"data: {json.dumps({'type': 'title', 'title': conv.title})}\n\n"
                    )

            await db.commit()

        except Exception:
            logger.exception("Background chat task failed for conv %s", conv_id)
            async with async_session_maker() as cleanup_db:
                try:
                    r = await cleanup_db.execute(
                        select(DashboardConversation).where(DashboardConversation.id == conv_id)
                    )
                    c = r.scalar_one_or_none()
                    if c is not None:
                        c.is_running = False
                        c.has_unread = False
                    await cleanup_db.commit()
                except Exception:
                    pass
            await queue.put(
                f"data: {json.dumps({'type': 'error', 'text': 'Processing failed'})}\n\n"
            )
        finally:
            await queue.put(f"data: {json.dumps({'type': 'done'})}\n\n")
            await queue.put(None)  # sentinel
```

- [ ] **Step 3: Replace stream_message endpoint with fire-and-forget version**

Find the existing `@router.post("/{conversation_id}/messages")` handler in `chats.py` and replace its entire body (keep the decorator and signature intact but change return type and body):

```python
@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    http_request: Request,
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """Save user message, start background task, return 202."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)

    msg_result = await db.execute(
        select(DashboardMessage)
        .where(DashboardMessage.conversation_id == conversation_id)
        .order_by(DashboardMessage.created_at)
    )
    existing_messages = msg_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in existing_messages[-25:]]

    credential = await get_accessible_credential(
        db, uuid.UUID(body.credential_id), current_user.id
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    if credential.type not in (CredentialType.openai, CredentialType.google, CredentialType.custom):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential must be an LLM type (OpenAI, Google, or Custom)",
        )

    config = decrypt_config(credential.encrypted_config)
    client, provider = get_openai_client(credential.type, config)
    attachment = (
        FileAttachment(name=body.attachment.name, kind=body.attachment.kind, content=body.attachment.content)
        if body.attachment
        else None
    )
    user_message = _build_user_message(body.content, attachment)
    messages = list(history[-MAX_DASHBOARD_CHAT_HISTORY:])
    messages.append(user_message)

    trace_context = LLMTraceContext(
        user_id=current_user.id,
        credential_id=credential.id,
        workflow_id=None,
        node_label="Dashboard Chat",
        source="dashboard_chat",
    )
    workflows = await get_workflows_for_user_with_inputs(db, current_user.id)
    workflows_block = _format_workflows_for_prompt(workflows)
    agents_md = _load_agents_md_content()
    system_prompt = DASHBOARD_CHAT_SYSTEM_PROMPT
    if agents_md:
        system_prompt = (
            "## Heym Platform Context\n\n"
            "Use the following Heym platform documentation to answer questions about the platform, "
            "structure, commands, code style, and conventions:\n\n"
            + agents_md
            + "\n\n---\n\n"
            + system_prompt
        )
    if workflows_block:
        system_prompt = (
            system_prompt
            + "\n\nAvailable workflows (always check these first when user asks for information):\n"
            + workflows_block
        )
    if body.attachment:
        system_prompt = system_prompt + "\n\n" + _ATTACHMENT_ROUTING_INSTRUCTIONS

    public_base_url = build_public_base_url(http_request)
    should_generate_title = (
        len(existing_messages) == 0 and conversation.title == DEFAULT_CONVERSATION_TITLE
    )

    # Save user message and mark conversation as running
    db.add(DashboardMessage(
        conversation_id=conversation_id,
        role="user",
        content=user_message["content"],
    ))
    conversation.is_running = True
    conversation.has_unread = False
    await db.commit()

    # Create queue and start background task
    registry.create_queue(str(conversation_id))
    asyncio.create_task(
        _process_chat(
            conv_id=conversation_id,
            user_id=current_user.id,
            client=client,
            model=body.model,
            provider=provider,
            system_prompt=system_prompt,
            messages=messages,
            trace_context=trace_context,
            public_base_url=public_base_url,
            attachment=attachment,
            credential=credential,
            should_generate_title=should_generate_title,
            first_user_content=body.content,
        )
    )

    return SendMessageResponse(conversation_id=conversation_id)
```

- [ ] **Step 4: Add GET /{conversation_id}/stream endpoint**

Add this endpoint to `chats.py` after `send_message`:

```python
@router.get("/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE endpoint: subscribe to in-progress background task or get done immediately."""
    await _get_conversation_or_404(conversation_id, current_user.id, db)
    conv_id_str = str(conversation_id)

    queue = registry.get_queue(conv_id_str)

    async def event_generator() -> "AsyncGenerator[str, None]":
        if queue is None:
            # Task already done (server restart or completed before subscribe)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        registry.increment_subscribers(conv_id_str)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    # Sentinel: task finished
                    break
                yield item
        finally:
            remaining = registry.decrement_subscribers(conv_id_str)
            if remaining == 0:
                registry.remove_queue(conv_id_str)

    from collections.abc import AsyncGenerator

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5: Add PATCH /{conversation_id}/read endpoint**

Add after `stream_conversation`:

```python
@router.patch("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_conversation_read(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear the has_unread flag for a conversation."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    conversation.has_unread = False
    await db.commit()
```

- [ ] **Step 6: Fix get_conversation to include new fields**

In `chats.py`, find the `get_conversation` handler where it manually constructs `ConversationDetailResponse`. Replace its return statement with:

```python
return ConversationDetailResponse(
    id=conversation.id,
    title=conversation.title,
    is_pinned=conversation.is_pinned,
    is_running=conversation.is_running,
    has_unread=conversation.has_unread,
    created_at=conversation.created_at,
    updated_at=conversation.updated_at,
    messages=[MessageResponse.model_validate(m) for m in sorted_messages],
)
```

(The `list_conversations`, `create_conversation`, and `update_conversation` handlers use `ConversationResponse.model_validate(c)` which picks up the new fields automatically.)

- [ ] **Step 7: Remove inline AsyncGenerator import from stream_conversation**

In the `stream_conversation` function body written in Step 4, remove the `from collections.abc import AsyncGenerator` line — it is already imported at the top of `chats.py`. The type annotation on `event_generator` should read:

```python
async def event_generator() -> AsyncGenerator[str, None]:
```

without any inline import.

- [ ] **Step 8: Lint check**

```bash
cd backend && uv run ruff check app/api/chats.py
```

Expected: no errors.

---

## Task 5: Quick Prompts Endpoints + Startup Cleanup

**Files:**
- Modify: `backend/app/api/chats.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add GET /quick-prompts and PUT /quick-prompts to chats.py**

These are conversation-independent routes — add them near the top of chats.py (before `/{conversation_id}` routes to avoid path conflicts). Add after the `clear_conversations` route:

```python
DEFAULT_QUICK_PROMPTS: list[str] = [
    "List my workflows",
    "Show recent runs",
    "Show analytics today",
    "What's on my schedule?",
    "Run a workflow",
    "Show my teams",
    "Create a workflow",
]

MAX_QUICK_PROMPTS = 7
MAX_PROMPT_LENGTH = 200


@router.get("/quick-prompts", response_model=QuickPromptsResponse)
async def get_quick_prompts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuickPromptsResponse:
    """Return the current user's quick prompt list, falling back to defaults."""
    result = await db.execute(
        select(DashboardChatQuickPrompts).where(
            DashboardChatQuickPrompts.user_id == current_user.id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return QuickPromptsResponse(prompts=DEFAULT_QUICK_PROMPTS)
    return QuickPromptsResponse(prompts=row.prompts or DEFAULT_QUICK_PROMPTS)


@router.put("/quick-prompts", response_model=QuickPromptsResponse)
async def save_quick_prompts(
    body: QuickPromptsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuickPromptsResponse:
    """Save the user's quick prompt list (max 7 items, each max 200 chars)."""
    cleaned = [p.strip() for p in body.prompts if p.strip()][:MAX_QUICK_PROMPTS]
    for prompt in cleaned:
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Prompt exceeds {MAX_PROMPT_LENGTH} characters",
            )

    result = await db.execute(
        select(DashboardChatQuickPrompts).where(
            DashboardChatQuickPrompts.user_id == current_user.id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(DashboardChatQuickPrompts(user_id=current_user.id, prompts=cleaned))
    else:
        row.prompts = cleaned
    await db.commit()
    return QuickPromptsResponse(prompts=cleaned)
```

- [ ] **Step 2: Add startup cleanup to main.py**

In `backend/app/main.py`, find the `async def lifespan(app: FastAPI):` function. After the `await lock_service.start()` line, add:

```python
# Reset stale is_running flags from a previous server instance
async with async_session_maker() as _startup_db:
    await _startup_db.execute(
        sa.text("UPDATE dashboard_conversations SET is_running = false WHERE is_running = true")
    )
    await _startup_db.commit()
logger.info("Reset stale chat is_running flags")
```

Also add these imports near the top of `main.py` if not present:

```python
import sqlalchemy as sa
from app.db.session import async_session_maker
```

- [ ] **Step 3: Lint + run tests**

```bash
cd backend && uv run ruff check app/api/chats.py app/main.py && ./run_tests.sh
```

Expected: all tests pass.

---

## Task 6: Backend Tests

**Files:**
- Create: `backend/tests/test_chat_background_task.py`
- Create: `backend/tests/test_chat_quick_prompts.py`

- [ ] **Step 1: Write test_chat_background_task.py**

```python
# backend/tests/test_chat_background_task.py
import asyncio
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.chats import mark_conversation_read, send_message, stream_conversation
from app.db.models import DashboardConversation, DashboardMessage
from app.models.chat_schemas import MessageCreate
from app.services import chat_task_registry as registry


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_conversation(user_id: uuid.UUID, is_running: bool = False) -> DashboardConversation:
    conv = DashboardConversation()
    conv.id = uuid.uuid4()
    conv.user_id = user_id
    conv.title = "New Chat"
    conv.is_pinned = False
    conv.is_running = is_running
    conv.has_unread = False
    return conv


class SendMessageEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_returns_202_and_creates_task(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        body = MessageCreate(content="Hello", credential_id=str(uuid.uuid4()), model="gpt-4o-mini")

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                # _get_conversation_or_404
                MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
                # load history
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                # get_workflows_for_user_with_inputs
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            ]
        )
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_credential = MagicMock()
        mock_credential.type = "openai"
        mock_credential.id = uuid.uuid4()
        mock_credential.encrypted_config = b"enc"

        mock_request = MagicMock()
        mock_request.url.scheme = "http"
        mock_request.url.netloc = "localhost"

        with (
            patch("app.api.chats.get_accessible_credential", return_value=mock_credential),
            patch("app.api.chats.decrypt_config", return_value={"api_key": "k"}),
            patch("app.api.chats.get_openai_client", return_value=(MagicMock(), "OpenAI")),
            patch("app.api.chats.get_workflows_for_user_with_inputs", return_value=[]),
            patch("app.api.chats._load_agents_md_content", return_value=""),
            patch("app.api.chats._format_workflows_for_prompt", return_value=""),
            patch("app.api.chats.build_public_base_url", return_value="http://localhost"),
            patch("app.api.chats.asyncio.create_task") as mock_create_task,
        ):
            mock_create_task.return_value = None
            result = await send_message(mock_request, conv.id, body, user, mock_db)

        self.assertEqual(str(result.conversation_id), str(conv.id))
        mock_create_task.assert_called_once()
        # is_running should have been set to True on the conversation
        self.assertTrue(conv.is_running)


class MarkConversationReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_mark_read_clears_has_unread(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        conv.has_unread = True

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=conv))
        )
        mock_db.commit = AsyncMock()

        await mark_conversation_read(conv.id, user, mock_db)

        self.assertFalse(conv.has_unread)
        mock_db.commit.assert_called_once()

    async def test_mark_read_raises_404_for_unknown_conversation(self) -> None:
        from fastapi import HTTPException

        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with self.assertRaises(HTTPException) as ctx:
            await mark_conversation_read(uuid.uuid4(), user, mock_db)
        self.assertEqual(ctx.exception.status_code, 404)


class ChatTaskRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        registry.remove_queue("test-id")

    def test_create_and_get_queue(self) -> None:
        q = registry.create_queue("test-id")
        self.assertIsNotNone(registry.get_queue("test-id"))
        self.assertIs(registry.get_queue("test-id"), q)

    def test_subscriber_count_increments_and_decrements(self) -> None:
        registry.create_queue("test-id")
        self.assertEqual(registry.subscriber_count("test-id"), 0)
        registry.increment_subscribers("test-id")
        registry.increment_subscribers("test-id")
        self.assertEqual(registry.subscriber_count("test-id"), 2)
        remaining = registry.decrement_subscribers("test-id")
        self.assertEqual(remaining, 1)

    def test_remove_queue_cleans_up(self) -> None:
        registry.create_queue("test-id")
        registry.remove_queue("test-id")
        self.assertIsNone(registry.get_queue("test-id"))
        self.assertEqual(registry.subscriber_count("test-id"), 0)
```

- [ ] **Step 2: Write test_chat_quick_prompts.py**

```python
# backend/tests/test_chat_quick_prompts.py
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api.chats import DEFAULT_QUICK_PROMPTS, get_quick_prompts, save_quick_prompts
from app.db.models import DashboardChatQuickPrompts
from app.models.chat_schemas import QuickPromptsUpdate


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


class GetQuickPromptsTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_defaults_when_no_row_exists(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        result = await get_quick_prompts(user, mock_db)

        self.assertEqual(result.prompts, DEFAULT_QUICK_PROMPTS)

    async def test_returns_saved_prompts_when_row_exists(self) -> None:
        user = _make_user()
        row = DashboardChatQuickPrompts()
        row.user_id = user.id
        row.prompts = ["Custom prompt 1", "Custom prompt 2"]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row))
        )

        result = await get_quick_prompts(user, mock_db)

        self.assertEqual(result.prompts, ["Custom prompt 1", "Custom prompt 2"])


class SaveQuickPromptsTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_prompts_and_returns_them(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        body = QuickPromptsUpdate(prompts=["List workflows", "Show runs"])
        result = await save_quick_prompts(body, user, mock_db)

        self.assertEqual(result.prompts, ["List workflows", "Show runs"])
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_strips_empty_prompts(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        body = QuickPromptsUpdate(prompts=["Valid prompt", "  ", "", "Another"])
        result = await save_quick_prompts(body, user, mock_db)

        self.assertEqual(result.prompts, ["Valid prompt", "Another"])

    async def test_truncates_to_max_7_prompts(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        body = QuickPromptsUpdate(prompts=[f"Prompt {i}" for i in range(10)])
        result = await save_quick_prompts(body, user, mock_db)

        self.assertEqual(len(result.prompts), 7)

    async def test_rejects_prompt_exceeding_max_length(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        body = QuickPromptsUpdate(prompts=["x" * 201])
        with self.assertRaises(HTTPException) as ctx:
            await save_quick_prompts(body, user, mock_db)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_updates_existing_row(self) -> None:
        user = _make_user()
        existing_row = DashboardChatQuickPrompts()
        existing_row.user_id = user.id
        existing_row.prompts = ["old"]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_row))
        )
        mock_db.commit = AsyncMock()

        body = QuickPromptsUpdate(prompts=["new prompt"])
        result = await save_quick_prompts(body, user, mock_db)

        self.assertEqual(result.prompts, ["new prompt"])
        self.assertEqual(existing_row.prompts, ["new prompt"])
        mock_db.commit.assert_called_once()
```

- [ ] **Step 3: Run the new tests**

```bash
cd backend && uv run pytest tests/test_chat_background_task.py tests/test_chat_quick_prompts.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run full test suite**

```bash
cd backend && ./run_tests.sh
```

Expected: all tests pass.

---

## Task 7: Frontend Types + API Service

**Files:**
- Modify: `frontend/src/types/chat.ts`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Update Conversation type in chat.ts**

In `frontend/src/types/chat.ts`, update the `Conversation` interface:

```typescript
export interface Conversation {
  id: string
  title: string
  is_pinned: boolean
  is_running: boolean
  has_unread: boolean
  created_at: string
  updated_at: string
}
```

No other changes needed — `ConversationDetail` extends `Conversation` and picks up the new fields automatically.

- [ ] **Step 2: Add new chatApi methods to services/api.ts**

In `frontend/src/services/api.ts`, inside the `chatApi` object (after `clearConversations`), add:

```typescript
  sendMessage: async (
    id: string,
    content: string,
    credentialId: string,
    model: string,
    attachment: FileAttachmentPayload | null,
  ): Promise<void> => {
    await api.post(`/chats/${id}/messages`, {
      content,
      credential_id: credentialId,
      model,
      ...(attachment ? { attachment } : {}),
    });
  },

  subscribeStream: async (
    id: string,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (msg: string) => void,
    onStep?: (label: string) => void,
    onToolOutput?: (images: string[]) => void,
    onTitle?: (title: string) => void,
    onWorkflowCreated?: (workflow: WorkflowPreview) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const base = import.meta.env.VITE_API_URL || "";
    const url = `${base}/api/chats/${id}/stream`;
    const response = await fetch(url, {
      method: "GET",
      credentials: "include",
      signal,
    });
    if (!response.ok || !response.body) {
      onError(`HTTP ${response.status}`);
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let reading = true;
    while (reading) {
      const { done, value } = await reader.read();
      if (done) { reading = false; break; }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const parsed = JSON.parse(line.slice(6));
          if (parsed.type === "content") onChunk(parsed.text);
          else if (parsed.type === "done") { onDone(); reading = false; break; }
          else if (parsed.type === "error") onError(parsed.text);
          else if (parsed.type === "step" && typeof parsed.label === "string") {
            onStep?.(parsed.label);
          } else if (
            parsed.type === "tool_output" &&
            Array.isArray(parsed.images) &&
            parsed.images.length > 0
          ) {
            onToolOutput?.(parsed.images);
          } else if (parsed.type === "title" && typeof parsed.title === "string") {
            onTitle?.(parsed.title);
          } else if (
            parsed.type === "workflow_created" &&
            typeof parsed.workflow_id === "string" &&
            typeof parsed.workflow_name === "string" &&
            typeof parsed.workflow_url === "string" &&
            Array.isArray(parsed.nodes) &&
            Array.isArray(parsed.edges)
          ) {
            onWorkflowCreated?.({
              id: parsed.workflow_id,
              name: parsed.workflow_name,
              description: typeof parsed.workflow_description === "string"
                ? parsed.workflow_description
                : null,
              url: parsed.workflow_url,
              nodes: parsed.nodes,
              edges: parsed.edges,
            });
          }
        } catch {
          // ignore malformed lines
        }
      }
    }
  },

  markConversationRead: async (id: string): Promise<void> => {
    await api.patch(`/chats/${id}/read`);
  },

  getQuickPrompts: async (): Promise<string[]> => {
    const response = await api.get<{ prompts: string[] }>("/chats/quick-prompts");
    return response.data.prompts;
  },

  saveQuickPrompts: async (prompts: string[]): Promise<string[]> => {
    const response = await api.put<{ prompts: string[] }>("/chats/quick-prompts", { prompts });
    return response.data.prompts;
  },
```

- [ ] **Step 3: Typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

---

## Task 8: Pinia Store

**Files:**
- Modify: `frontend/src/stores/chat.ts`

- [ ] **Step 1: Add quickPrompts state and new actions**

In `frontend/src/stores/chat.ts`, inside `defineStore("chat", () => { ... })`:

After the existing `const activeAbortController = ref<AbortController | null>(null);` line, add:

```typescript
const quickPrompts = ref<string[]>([]);
```

- [ ] **Step 2: Add markConversationRead action**

Add after the `cancelStreaming` function:

```typescript
async function markConversationRead(id: string): Promise<void> {
  conversations.value = conversations.value.map((c) =>
    c.id === id ? { ...c, has_unread: false } : c,
  );
  try {
    await chatApi.markConversationRead(id);
  } catch {
    // best-effort; local state already cleared
  }
}

async function loadQuickPrompts(): Promise<void> {
  try {
    quickPrompts.value = await chatApi.getQuickPrompts();
  } catch {
    quickPrompts.value = [];
  }
}

async function saveQuickPrompts(prompts: string[]): Promise<void> {
  try {
    quickPrompts.value = await chatApi.saveQuickPrompts(prompts);
  } catch {
    // best-effort
  }
}
```

- [ ] **Step 3: Refactor sendMessage to use fire-and-forget pattern**

Replace the existing `sendMessage` function entirely in `stores/chat.ts` (find the function starting with `async function sendMessage(` and replace through its closing `}`). The new version no longer calls `chatApi.streamMessagePost` — it calls `chatApi.sendMessage` then `_subscribeToStream`. The new version calls `sendMessage` (POST 202) then `subscribeStream` (GET SSE):

```typescript
async function sendMessage(
  conversationId: string,
  content: string,
  credentialId: string,
  model: string,
  attachment: FileAttachmentPayload | null = null,
): Promise<void> {
  if (!activeConversation.value || activeConversation.value.id !== conversationId) return;

  const userMessage: Message = {
    id: crypto.randomUUID(),
    role: "user",
    content,
    ...(attachment ? { attachmentName: attachment.name } : {}),
    created_at: new Date().toISOString(),
  };
  activeConversation.value = {
    ...activeConversation.value,
    messages: [...activeConversation.value.messages, userMessage],
  };
  void _writeCachedConversation(activeConversation.value);

  // Mark conversation as running locally before the 202 comes back
  conversations.value = conversations.value.map((c) =>
    c.id === conversationId ? { ...c, is_running: true } : c,
  );

  isStreaming.value = true;
  streamingContent.value = "";
  streamingImages.value = [];
  streamingSteps.value = [];
  streamingWorkflowPreview.value = null;
  activeAbortController.value = new AbortController();

  try {
    await chatApi.sendMessage(conversationId, content, credentialId, model, attachment);
    await _subscribeToStream(conversationId, activeAbortController.value.signal);
  } catch {
    isStreaming.value = false;
    streamingContent.value = "";
    streamingImages.value = [];
    streamingSteps.value = [];
    streamingWorkflowPreview.value = null;
    conversations.value = conversations.value.map((c) =>
      c.id === conversationId ? { ...c, is_running: false } : c,
    );
    activeAbortController.value = null;
  }
}
```

- [ ] **Step 4: Add _subscribeToStream helper**

Add this private helper after `sendMessage`:

```typescript
async function _subscribeToStream(conversationId: string, signal: AbortSignal): Promise<void> {
  await chatApi.subscribeStream(
    conversationId,
    (text) => {
      streamingContent.value += text;
    },
    () => {
      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: streamingContent.value,
        ...(streamingImages.value.length > 0 ? { images: [...streamingImages.value] } : {}),
        ...(streamingWorkflowPreview.value ? { workflowPreview: streamingWorkflowPreview.value } : {}),
        created_at: new Date().toISOString(),
      };
      if (activeConversation.value?.id === conversationId) {
        activeConversation.value = {
          ...activeConversation.value,
          messages: [...activeConversation.value.messages, assistantMessage],
        };
        void _writeCachedConversation(activeConversation.value);
      }
      streamingContent.value = "";
      streamingImages.value = [];
      streamingSteps.value = [];
      streamingWorkflowPreview.value = null;
      isStreaming.value = false;
      activeAbortController.value = null;
      conversations.value = conversations.value.map((c) =>
        c.id === conversationId ? { ...c, is_running: false } : c,
      );
      _refreshConversationTimestamp(conversationId);
    },
    (_err) => {
      isStreaming.value = false;
      streamingContent.value = "";
      streamingImages.value = [];
      streamingSteps.value = [];
      streamingWorkflowPreview.value = null;
      conversations.value = conversations.value.map((c) =>
        c.id === conversationId ? { ...c, is_running: false } : c,
      );
      activeAbortController.value = null;
    },
    (label) => { streamingSteps.value = [...streamingSteps.value, label]; },
    (images) => { streamingImages.value = [...streamingImages.value, ...images]; },
    (title) => { _patchConversationTitle(conversationId, title); },
    (workflow) => { streamingWorkflowPreview.value = workflow; },
    signal,
  );
}
```

- [ ] **Step 5: Add auto-reconnect on loadConversation**

In `loadConversation`, after setting `activeConversation.value = fetched;`, add:

```typescript
// Auto-reconnect if this conversation has an active background task
if (fetched.is_running && activeAbortController.value === null) {
  isStreaming.value = true;
  activeAbortController.value = new AbortController();
  void _subscribeToStream(id, activeAbortController.value.signal);
}
```

Also call `markConversationRead(id)` if `fetched.has_unread`:

```typescript
if (fetched.has_unread) {
  void markConversationRead(id);
}
```

- [ ] **Step 6: Export new actions and state**

In the `return` statement of the store, add:

```typescript
quickPrompts,
markConversationRead,
loadQuickPrompts,
saveQuickPrompts,
```

- [ ] **Step 7: Typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

---

## Task 9: ChatListItem Visual Updates

**Files:**
- Modify: `frontend/src/components/Chat/ChatListItem.vue`

- [ ] **Step 1: Add is_running and has_unread to Props**

The `conversation` prop already carries the full `Conversation` object which now has `is_running` and `has_unread`. No Props interface change needed — just use them.

- [ ] **Step 2: Add isActive prop usage for dot visibility**

`isActive` is already a prop. No change needed.

- [ ] **Step 3: Update template — add running bar and unread dot**

Replace the outer `<div>` in the template (the one with `@click="emit('select', conversation.id)"`) so it reads:

```html
<div
  :class="cn(
    'group relative flex items-center border-radius-lg cursor-pointer transition-colors overflow-hidden',
    isActive
      ? 'bg-primary/10 text-primary'
      : 'hover:bg-muted/60 text-foreground'
  )"
  @click="handleSelect"
>
  <!-- Feature 1: left-edge running bar -->
  <div
    :class="[
      'self-stretch w-[3px] shrink-0 rounded-r-full',
      conversation.is_running ? 'chat-item-bar--running' : '',
    ]"
  />

  <div class="flex-1 min-w-0 px-3 py-2">
    <!-- existing content unchanged -->
    <template v-if="isEditing">
      <input
        ref="editInputRef"
        v-model="editTitle"
        class="w-full text-sm bg-background border border-border rounded px-1 py-0.5 outline-none"
        @keydown="onEditKeydown"
        @blur="commitEdit"
        @click.stop
      >
    </template>
    <template v-else>
      <span
        class="block text-sm truncate leading-5"
        @dblclick.stop="startEdit"
      >
        {{ conversation.title }}
      </span>
    </template>
  </div>

  <!-- Feature 2: unread dot -->
  <div
    v-if="conversation.has_unread && !isActive"
    class="w-2 h-2 rounded-full bg-primary shrink-0 mr-2.5 shadow-[0_0_6px_rgba(99,102,241,0.6)]"
  />

  <!-- existing hover actions (pin/rename/delete) — keep unchanged -->
  <div
    v-if="!isEditing && !isConfirmingDelete"
    class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity pr-1"
    @click.stop
  >
    <!-- ... existing buttons ... -->
  </div>
  <!-- existing delete confirm — keep unchanged -->
</div>
```

- [ ] **Step 4: Add handleSelect method and CSS animation**

In the `<script setup>` section, replace `emit('select', conversation.id)` call in the template with a method. Add to the script:

```typescript
function handleSelect(): void {
  emit("select", conversation.id);
}
```

The `markConversationRead` is called in the store's `loadConversation` automatically (via `has_unread` check), so no explicit call needed here.

- [ ] **Step 5: Add CSS for running bar animation**

In the `<style scoped>` section (add if not present), add:

```css
.chat-item-bar--running {
  background: linear-gradient(
    to bottom,
    transparent 0%,
    hsl(var(--primary)) 30%,
    hsl(var(--primary) / 0.7) 50%,
    hsl(var(--primary)) 70%,
    transparent 100%
  );
  background-size: 100% 300%;
  animation: chat-bar-shimmer 1.6s ease-in-out infinite;
}

@keyframes chat-bar-shimmer {
  0%   { background-position: 0% 0%; }
  50%  { background-position: 0% 100%; }
  100% { background-position: 0% 0%; }
}
```

- [ ] **Step 6: Fix class string for outer div (use cn properly)**

The outer div class uses `cn(...)`. Update to keep the `rounded-lg` and `overflow-hidden` without breaking existing layout:

```html
<div
  :class="cn(
    'group relative flex items-center rounded-lg cursor-pointer transition-colors overflow-hidden mb-0.5',
    isActive
      ? 'bg-primary/10 text-primary'
      : 'hover:bg-muted/60 text-foreground'
  )"
  @click="handleSelect"
>
```

- [ ] **Step 7: Typecheck + lint**

```bash
cd frontend && bun run typecheck && bun run lint
```

Expected: no errors.

---

## Task 10: ChatConversation — Drag-to-Import

**Files:**
- Modify: `frontend/src/components/Chat/ChatConversation.vue`

- [ ] **Step 1: Add isDraggingFile ref**

In the `<script setup>` section, after existing refs, add:

```typescript
const isDraggingFile = ref(false);
let dragCounter = 0; // counts nested dragenter/dragleave pairs
```

- [ ] **Step 2: Add drag event handlers**

Add these functions in the script section:

```typescript
function handleDragEnter(event: DragEvent): void {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  dragCounter++;
  isDraggingFile.value = true;
}

function handleDragOver(event: DragEvent): void {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
}

function handleDragLeave(_event: DragEvent): void {
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    isDraggingFile.value = false;
  }
}

async function handleDrop(event: DragEvent): Promise<void> {
  event.preventDefault();
  dragCounter = 0;
  isDraggingFile.value = false;
  const file = event.dataTransfer?.files[0];
  if (file) {
    await processFile(file);
  }
}
```

- [ ] **Step 3: Bind drag events to the chat root div**

Find the root `<div ref="chatRootRef" ...>` in the template and add:

```html
@dragenter="handleDragEnter"
@dragover="handleDragOver"
@dragleave="handleDragLeave"
@drop="handleDrop"
```

- [ ] **Step 4: Add drag overlay**

Inside the root div, add the overlay as the first child element:

```html
<Transition name="fade">
  <div
    v-if="isDraggingFile"
    class="absolute inset-0 z-30 flex items-center justify-center pointer-events-none"
  >
    <div class="absolute inset-2 rounded-xl border-2 border-dashed border-primary/60 bg-primary/5 flex items-center justify-center gap-3">
      <Paperclip class="w-5 h-5 text-primary/70" />
      <span class="text-sm font-medium text-primary/70">Drop to attach</span>
    </div>
  </div>
</Transition>
```

- [ ] **Step 5: Add fade transition CSS**

In `<style scoped>`:

```css
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
```

- [ ] **Step 6: Typecheck + lint**

```bash
cd frontend && bun run typecheck && bun run lint
```

Expected: no errors.

---

## Task 11: Quick Prompts Composable + ChatConversation Empty State

**Files:**
- Create: `frontend/src/composables/useQuickPrompts.ts`
- Modify: `frontend/src/components/Chat/ChatConversation.vue`

- [ ] **Step 1: Create useQuickPrompts composable**

```typescript
// frontend/src/composables/useQuickPrompts.ts
import { ref } from "vue";
import { useChatStore } from "@/stores/chat";

export function useQuickPrompts() {
  const chatStore = useChatStore();
  const editingIndex = ref<number | null>(null);
  const editingValue = ref("");

  function startEdit(index: number): void {
    editingIndex.value = index;
    editingValue.value = chatStore.quickPrompts[index] ?? "";
  }

  function cancelEdit(): void {
    editingIndex.value = null;
    editingValue.value = "";
  }

  async function commitEdit(): Promise<void> {
    if (editingIndex.value === null) return;
    const trimmed = editingValue.value.trim();
    if (!trimmed) {
      cancelEdit();
      return;
    }
    const updated = [...chatStore.quickPrompts];
    updated[editingIndex.value] = trimmed;
    editingIndex.value = null;
    editingValue.value = "";
    await chatStore.saveQuickPrompts(updated);
  }

  function onEditKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
      event.preventDefault();
      void commitEdit();
    }
    if (event.key === "Escape") {
      cancelEdit();
    }
  }

  return { editingIndex, editingValue, startEdit, cancelEdit, commitEdit, onEditKeydown };
}
```

- [ ] **Step 2: Load quick prompts on mount**

In `ChatConversation.vue`, in `onMounted`, add:

```typescript
void chatStore.loadQuickPrompts();
```

- [ ] **Step 3: Import useQuickPrompts in ChatConversation**

In the script imports section of `ChatConversation.vue`, add:

```typescript
import { Pencil } from "lucide-vue-next";
import { useQuickPrompts } from "@/composables/useQuickPrompts";
```

And in the script body:

```typescript
const { editingIndex, editingValue, startEdit, cancelEdit, commitEdit, onEditKeydown } =
  useQuickPrompts();
```

- [ ] **Step 4: Add sendQuickPrompt function**

```typescript
async function sendQuickPrompt(text: string): Promise<void> {
  if (chatStore.isStreaming || !canSendMessage.value) return;
  input.value = text;
  await nextTick();
  await send();
}
```

- [ ] **Step 5: Add quick-prompt empty state to the template**

Find the messages scroll area in `ChatConversation.vue`. The empty state is currently shown when `messages.length === 0` and `!chatStore.isStreaming` (the loading spinner area). Add the quick-prompt list inside the messages area when `messages.length === 0`:

```html
<!-- Quick prompts: only shown in empty conversation, vertically centered in messages area -->
<div
  v-if="messages.length === 0 && !chatStore.isStreaming && !chatStore.isLoadingMessages"
  class="flex-1 flex flex-col items-center justify-center gap-3 px-4 py-6"
>
  <Bot class="w-8 h-8 opacity-20" />
  <p class="text-xs text-muted-foreground text-center mb-2">
    Ask me anything or pick a prompt below
  </p>
  <div class="flex flex-col gap-1.5 w-full max-w-sm">
    <div
      v-for="(prompt, idx) in chatStore.quickPrompts"
      :key="idx"
      class="group flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-lg border border-border/40 bg-background/60 hover:border-primary/40 hover:bg-primary/5 transition-colors cursor-pointer text-sm text-muted-foreground hover:text-foreground"
      @click="editingIndex !== idx && sendQuickPrompt(prompt)"
    >
      <template v-if="editingIndex === idx">
        <input
          v-model="editingValue"
          class="flex-1 bg-transparent border-none outline-none text-sm text-foreground"
          @keydown="onEditKeydown"
          @blur="commitEdit"
          @click.stop
        >
        <button
          type="button"
          class="shrink-0 p-0.5 rounded hover:bg-muted/60"
          aria-label="Save"
          @click.stop="commitEdit"
        >
          <Check class="w-3.5 h-3.5 text-primary" />
        </button>
      </template>
      <template v-else>
        <span class="flex-1 truncate">{{ prompt }}</span>
        <button
          type="button"
          class="shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-muted/60 transition-opacity"
          aria-label="Edit prompt"
          @click.stop="startEdit(idx)"
        >
          <Pencil class="w-3 h-3 text-muted-foreground" />
        </button>
      </template>
    </div>
  </div>
</div>
```

The `Check` icon is already imported in `ChatConversation.vue`. Verify `Pencil` is imported (added in Step 3).

- [ ] **Step 6: Typecheck + lint**

```bash
cd frontend && bun run typecheck && bun run lint
```

Expected: no errors.

---

## Task 12: Final Integration Check

- [ ] **Step 1: Run full backend checks**

```bash
cd /path/to/heymrun && ./check.sh
```

Expected: ruff format passes, all backend tests pass.

- [ ] **Step 2: Start services and smoke test**

```bash
./run.sh --no-debug
```

Open `http://localhost:4017/chats` in the browser.

Verify:
1. Empty conversation shows 7 prompt chips
2. Click a prompt → message auto-sends, prompt list disappears
3. Hover a prompt → pencil icon appears; click it → inline edit; Enter saves
4. Send a message while sidebar shows another conversation → that item shows animated left bar
5. After assistant responds → if not viewing that conversation, unread dot appears
6. Navigate to that conversation → dot disappears
7. Drag a file onto the chat area → dashed overlay appears; drop → file attaches

- [ ] **Step 3: Commit**

```bash
git add \
  backend/alembic/versions/064_chat_background_and_prompts.py \
  backend/app/db/models.py \
  backend/app/models/chat_schemas.py \
  backend/app/services/chat_task_registry.py \
  backend/app/api/chats.py \
  backend/app/main.py \
  backend/tests/test_chat_background_task.py \
  backend/tests/test_chat_quick_prompts.py \
  frontend/src/types/chat.ts \
  frontend/src/services/api.ts \
  frontend/src/stores/chat.ts \
  frontend/src/components/Chat/ChatListItem.vue \
  frontend/src/components/Chat/ChatConversation.vue \
  frontend/src/composables/useQuickPrompts.ts

git commit -m "feat: chat background tasks, running/unread indicators, drag-to-import, quick prompts"
```
