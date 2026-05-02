# Dashboard Chat — Design Spec

**Date:** 2026-05-02
**Status:** Approved

## Overview

Persistent, multi-session chat accessible from the dashboard. Users can create, rename, pin, and delete named conversations. Each conversation has a unique URL and its history is stored in the database so it can be resumed across sessions.

---

## Layout & UX

- Clicking the 💬 icon in the left icon rail navigates to `/chats`.
- `/chats` and `/chats/:id` both render `ChatsView.vue`.
- `ChatsView` is split into two areas:
  - **Left:** `ChatListPanel.vue` — collapsible sidebar listing all conversations.
  - **Right:** `ChatConversation.vue` — the active conversation (messages + input).
- The sidebar can be toggled open/closed via a chevron button; state is persisted to localStorage (same pattern as `quickDrawer.ts`).
- `/chats` with no `:id` shows an empty right pane prompting the user to select or create a chat.

### Chat List Panel

- "New Chat" button at the top.
- Scrollable list of `ChatListItem` rows.
- Pinned conversations appear above a `📌 Pinned` separator; unpinned below, sorted by `updated_at` descending.
- Each row shows: title, relative timestamp.
- On hover: pencil (rename), pin/unpin toggle, trash (delete).
- Active row highlighted with a left-border accent.

### Chat Conversation

- Editable title at the top — click to rename inline (same action as the list-item rename).
- Credential + model selector (same pattern as existing `DashboardChatPanel.vue`).
- Scrollable message list with user/assistant bubbles; assistant content rendered as markdown.
- Textarea input + send button; streams assistant reply live.

---

## Routing

```
/chats        → ChatsView.vue   meta: { requiresAuth: true }
/chats/:id    → ChatsView.vue   meta: { requiresAuth: true }
```

`DashboardNav.vue` gets a Chat icon link that always navigates to `/chats`.

---

## Backend

### DB Models (`backend/app/db/models.py`)

**`DashboardConversation`** — table `dashboard_conversations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `default=uuid.uuid4` |
| `user_id` | UUID FK → `users.id` | `ondelete=CASCADE`, indexed |
| `title` | String(255) | default `"New Chat"` |
| `is_pinned` | Boolean | default `False` |
| `created_at` | DateTime(tz) | `server_default=func.now()` |
| `updated_at` | DateTime(tz) | `server_default=func.now()`, `onupdate=func.now()` |

Has `relationship("DashboardMessage", cascade="all, delete-orphan")`.

**`DashboardMessage`** — table `dashboard_messages`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `default=uuid.uuid4` |
| `conversation_id` | UUID FK → `dashboard_conversations.id` | `ondelete=CASCADE`, indexed |
| `role` | String(20) | `"user"` or `"assistant"` |
| `content` | Text | |
| `created_at` | DateTime(tz) | `server_default=func.now()` |

### Migration

`backend/alembic/versions/061_add_dashboard_conversations.py`

Creates both tables with all indexes and foreign key constraints.

### API Endpoints (`backend/app/api/routes/chats.py`)

All endpoints require `get_current_user()`. Users may only access their own conversations.

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/chats` | List conversations — pinned first, then `updated_at` DESC |
| `POST` | `/api/chats` | Create new conversation (title defaults to `"New Chat"`) |
| `GET` | `/api/chats/{id}` | Get conversation metadata + all messages |
| `PUT` | `/api/chats/{id}` | Update `title` and/or `is_pinned` |
| `DELETE` | `/api/chats/{id}` | Delete conversation (cascades messages) |
| `POST` | `/api/chats/{id}/messages` | Send user message, stream assistant reply (SSE) |

The streaming endpoint (`POST /api/chats/{id}/messages`):
1. Validates conversation ownership.
2. Persists the user message to `dashboard_messages`.
3. Streams assistant reply via the existing LLM streaming infrastructure (same as `aiApi.dashboardChatStream()`); accepts `credential_id`, `model`, `content`.
4. Persists the completed assistant message once the stream closes.

### Schemas (`backend/app/models/chat_schemas.py`)

- `ConversationCreate` — `title?: str`
- `ConversationUpdate` — `title?: str`, `is_pinned?: bool`
- `ConversationResponse` — all columns
- `ConversationListResponse` — `conversations: list[ConversationResponse]`
- `ConversationDetailResponse` — `ConversationResponse` + `messages: list[MessageResponse]`
- `MessageCreate` — `content: str`, `credential_id: str`, `model: str`
- `MessageResponse` — `id`, `role`, `content`, `created_at`

---

## Frontend

### Store (`frontend/src/stores/chat.ts`)

```typescript
// State
conversations: Ref<DashboardConversation[]>  // pinned first, then updated_at DESC
activeId: Ref<string | null>                  // mirrors route :id param
messages: Ref<DashboardMessage[]>             // for the active conversation
sidebarOpen: Ref<boolean>                     // persisted to localStorage

// Actions
fetchConversations(): Promise<void>
createConversation(): Promise<void>           // POST → navigate to /chats/:newId
loadConversation(id: string): Promise<void>   // GET detail → set messages
renameConversation(id: string, title: string): Promise<void>
togglePin(id: string): Promise<void>          // re-sorts list after update
deleteConversation(id: string): Promise<void> // navigate to /chats if was active
sendMessage(id: string, content: string, credentialId: string, model: string): Promise<void>
  // streams → optimistic user bubble → live assistant chunks → confirm both in store
```

Sidebar open/closed state key in localStorage: `"heym-chat-sidebar-open"`.

### Components

**`frontend/src/views/ChatsView.vue`**
- Orchestration only. Reads `:id` from `useRoute()`. On mount and route change: always calls `fetchConversations()`; calls `loadConversation(id)` in parallel only when `:id` is present. Renders `ChatListPanel` + `ChatConversation` side by side.

**`frontend/src/components/Chat/ChatListPanel.vue`**
- Collapsible sidebar. Toggle button binds to `chatStore.sidebarOpen`.
- "New Chat" button calls `chatStore.createConversation()`.
- Renders `ChatListItem` for each conversation; pinned section separated by a label.
- Panel is scrollable (`overflow-y: auto`).

**`frontend/src/components/Chat/ChatListItem.vue`**
- Props: `conversation: DashboardConversation`, `isActive: boolean`.
- Title display; hover shows rename (pencil → inline `<input>`), pin toggle, delete (trash → confirm popover).
- Rename: blur or Enter commits `chatStore.renameConversation()`.
- Delete: confirm popover → `chatStore.deleteConversation()`.

**`frontend/src/components/Chat/ChatConversation.vue`**
- Editable title in header (same rename flow as `ChatListItem`).
- Credential + model selectors.
- Scrollable message list; assistant messages rendered via existing markdown renderer with DOMPurify.
- Textarea + send; calls `chatStore.sendMessage()`.
- On stream: appends chunks live to the assistant bubble.

### Service additions (`frontend/src/services/api.ts`)

```typescript
export const chatApi = {
  list: () => api.get<ConversationListResponse>('/api/chats'),
  create: (title?: string) => api.post<ConversationResponse>('/api/chats', { title }),
  get: (id: string) => api.get<ConversationDetailResponse>(`/api/chats/${id}`),
  update: (id: string, data: ConversationUpdate) => api.put<ConversationResponse>(`/api/chats/${id}`, data),
  delete: (id: string) => api.delete(`/api/chats/${id}`),
  // streaming handled via fetch SSE (same pattern as dashboardChatStream)
  streamMessage: (id: string, payload: MessageCreate, onChunk, onDone, onError, signal?) => void
}
```

---

## Data Flows

| Action | Flow |
|---|---|
| **Create** | "New Chat" → `POST /api/chats` → store prepends → navigate `/chats/:newId` |
| **Send message** | Submit → optimistic user bubble → SSE stream → live chunks → stream close → both messages in store |
| **Rename** | Inline input blur/Enter → `PUT /api/chats/:id {title}` → update store list + header |
| **Pin** | Pin icon → `PUT /api/chats/:id {is_pinned: true/false}` → re-sort store list |
| **Delete** | Trash → confirm → `DELETE /api/chats/:id` → remove from store → if active, navigate `/chats` |
| **Hard reload on /chats/:id** | Mount → `fetchConversations()` + `loadConversation(id)` parallel → render |

---

## Error Handling

- **Stream failure:** show inline error bubble; allow user to resend.
- **404 on `/chats/:id`:** redirect to `/chats` with a toast notification.
- **403 (wrong user):** toast + redirect to `/chats`.
- All other API errors: typed axios catch → toast (consistent with rest of app).

---

## Testing

New file: `backend/tests/test_dashboard_chats.py`

Covers:
- Create conversation
- List conversations (pinned ordering)
- Get conversation with messages
- Rename conversation
- Toggle pin
- Delete conversation (cascade)
- Send message — user message persisted, assistant message persisted after stream
- Authorization: user cannot access another user's conversation (expects 403/404)
