# Chat Background Features Design
**Date:** 2026-05-13  
**Status:** Approved

---

## Overview

Four features added to the `/chats` screen:

1. **Running indicator** — animated left-edge bar in the sidebar for conversations with an active background task
2. **Unread dot** — notification indicator on the sidebar item when assistant finishes and user hasn't read the result
3. **Drag-to-import** — drop a file anywhere on the chat area to attach it
4. **Quick prompts** — vertical list of up to 7 editable prompts shown in the empty-chat state, auto-submit on click, persisted to DB per user

---

## Architecture Decision: Background Task Model

**Chosen: "Fire and forget" with asyncio.Queue**

- When a message arrives at `POST /api/chat/conversations/{id}/messages`, the backend immediately launches `asyncio.create_task(process_chat(...))` and returns `202 Accepted`
- The background task writes SSE chunks to a per-conversation `asyncio.Queue`
- A separate `GET /api/chat/conversations/{id}/stream` SSE endpoint subscribes to that queue
- If the browser is closed mid-stream and reopened, the frontend reconnects to the SSE endpoint; if the task is still running it resumes receiving chunks, if already finished it receives a `done` event with no content (messages are loaded from DB)
- When the task completes: assistant message saved to DB, `is_running=False`, `has_unread=True` (only if no active SSE subscriber on that conversation)
- In-memory queues do not survive server restarts; on reconnect after restart `is_running` is stale — a startup cleanup sets all `is_running=True` records to `False`

---

## Database Changes

### Migration `064_chat_background_and_prompts`

```sql
-- dashboard_conversations: two new columns
ALTER TABLE dashboard_conversations
  ADD COLUMN is_running BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN has_unread BOOLEAN NOT NULL DEFAULT false;

-- new table: one row per user, upsert on save
CREATE TABLE dashboard_chat_quick_prompts (
  user_id    UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  prompts    JSONB NOT NULL DEFAULT '[]',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Backend Changes

### New / Modified Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/conversations/{id}/messages` | Accept user message, start background task, return `202` |
| `GET` | `/api/chat/conversations/{id}/stream` | SSE — subscribe to in-progress or finished result |
| `PATCH` | `/api/chat/conversations/{id}/read` | Set `has_unread=False` |
| `GET` | `/api/chat/quick-prompts` | Return current user's prompts list |
| `PUT` | `/api/chat/quick-prompts` | Replace current user's prompts list (max 7 items) |
| `GET` | `/api/chat/conversations` | Updated response includes `is_running`, `has_unread` |
| `GET` | `/api/chat/conversations/{id}` | Updated response includes `is_running`, `has_unread` |

The existing `POST /dashboard-chat` endpoint is **removed** and replaced by the two-step `POST .../messages` + `GET .../stream` pair.

### Background Task Registry

```python
# app/services/chat_task_registry.py
_queues: dict[str, asyncio.Queue] = {}       # conv_id → Queue[SSEChunk | None]
_subscriber_counts: dict[str, int] = {}       # conv_id → active SSE subscriber count

def create_queue(conv_id: str) -> asyncio.Queue: ...
def get_queue(conv_id: str) -> asyncio.Queue | None: ...
def remove_queue(conv_id: str) -> None: ...
def increment_subscribers(conv_id: str) -> None: ...
def decrement_subscribers(conv_id: str) -> int: ...  # returns remaining count
```

### process_chat() flow

```
async def process_chat(conv_id, content, credential_id, model, attachment):
    # opens its own DB session via async_session_factory() — NOT FastAPI get_db()
    queue = registry.get_queue(conv_id)
    try:
        # existing stream_dashboard_chat logic — writes chunks to queue instead of yielding
        async for chunk in stream_dashboard_chat(...):
            await queue.put(chunk)
        # save assistant message to DB
        await save_assistant_message(conv_id, full_content, db_session_factory)
        await set_conversation_flags(conv_id, is_running=False,
                                     has_unread=(registry.subscriber_count(conv_id) == 0))
        await queue.put(None)  # sentinel: done
    except Exception:
        await set_conversation_flags(conv_id, is_running=False, has_unread=False)
        await queue.put({"type": "error", "text": "..."})
        await queue.put(None)
    finally:
        # queue removed after last subscriber leaves, not here
```

### Startup cleanup

In `app/main.py` lifespan handler:
```python
await db.execute("UPDATE dashboard_conversations SET is_running = false WHERE is_running = true")
```

---

## Frontend Changes

### Service Layer (`services/api.ts`)

`chatApi.streamMessagePost()` is removed. Replaced by:
- `chatApi.sendMessage(convId, payload)` → `POST .../messages` (returns `202`)
- `chatApi.subscribeStream(convId, callbacks)` → opens `EventSource` on `GET .../stream`, wires chunk/done/error callbacks


### Pinia Store (`stores/chat.ts`)

New fields on `Conversation` type (mirrors backend response):
```ts
is_running: boolean
has_unread: boolean
```

Store additions:
- `sendMessage()` refactored: calls `POST .../messages` → then opens `GET .../stream` SSE; on page load, auto-reconnects to stream if `is_running=true`
- `markConversationRead(id)`: calls `PATCH .../read`, clears `has_unread` locally
- `loadQuickPrompts()`: `GET /api/chat/quick-prompts`
- `saveQuickPrompts(prompts)`: `PUT /api/chat/quick-prompts`

### ChatListItem.vue

- Left-edge 3px bar: rendered always, `running` class added when `conversation.is_running`; CSS gradient shimmer animation
- Right-side 8px dot: rendered when `conversation.has_unread && !isActive`
- On click: calls `chatStore.markConversationRead(conversation.id)` before routing

### ChatConversation.vue

**Feature 3 — Drag-to-import:**
- `dragover` on the `.chat-input-area` wrapper (or the full conversation root): set `isDraggingFile=true`, show dashed overlay
- `dragleave` / `drop`: set `isDraggingFile=false`
- On `drop`: call `processFile(event.dataTransfer.files[0])` from `useFileAttachment`
- Overlay: absolutely positioned over the chat area, visible only when `isDraggingFile`

**Feature 4 — Quick prompts:**
- New composable `useQuickPrompts()` handles load/save/defaults
- Default 7 English prompts (hardcoded fallback if DB empty):
  1. "List my workflows"
  2. "Show recent runs"
  3. "Show analytics today"
  4. "What's on my schedule?"
  5. "Run a workflow"
  6. "Show my teams"
  7. "Create a workflow"
- Shown only when `messages.length === 0` (empty conversation), inside the messages area, vertically centered
- Each prompt: row with text + pencil icon (hover-only); click → fill input + `send()`; pencil click → inline edit mode, Enter/blur → save → `PUT /api/chat/quick-prompts`
- If attachment is active when prompt clicked: message sent with the attachment (existing attachment payload logic reused)

---

## Pydantic Schema Changes (`chat_schemas.py`)

```python
class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    is_running: bool       # NEW
    has_unread: bool       # NEW
    created_at: datetime
    updated_at: datetime

class QuickPromptsResponse(BaseModel):
    prompts: list[str]

class QuickPromptsUpdate(BaseModel):
    prompts: list[str]     # max 7 items, each max 200 chars
```

---

## Testing

Backend tests (`backend/tests/`):
- `test_chat_background_task.py` — message POST returns 202, task sets flags, stream SSE delivers chunks and done sentinel
- `test_chat_quick_prompts.py` — GET defaults, PUT saves, PUT with >7 items returns 422
- `test_chat_read.py` — PATCH read clears `has_unread`
- `test_chat_startup_cleanup.py` — lifespan sets stale `is_running` to false

No frontend tests (consistent with current project policy).

---

## Constraints & Edge Cases

- **Max prompts:** 7. Backend validates and returns 422 if exceeded.
- **Empty prompt text:** stripped; if empty after strip, ignored on save.
- **Server restart:** `is_running` stale rows cleared on startup; frontend shows no spinner for those conversations on reload.
- **Multiple tabs:** If user has two tabs open for the same conversation, both subscribe to the queue. `has_unread` is only set if subscriber count = 0 at task completion.
- **Prompt click during streaming:** Disabled while `chatStore.isStreaming`.
- **Drag outside input area:** Only the chat conversation root element listens for drag events; dragging over the sidebar does not trigger the overlay.
