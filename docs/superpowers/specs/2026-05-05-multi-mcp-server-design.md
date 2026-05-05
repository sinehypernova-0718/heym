# Multi-MCP Server (Named Clusters) Design

**Date:** 2026-05-05
**Status:** Approved

## Problem

All of a user's MCP-enabled workflows are currently exposed as a single flat list of tools on one endpoint (`/api/mcp/sse`). At scale this becomes unmanageable — 1000 workflows cannot all be tools on one server. Users need to group workflows into named MCP servers (clusters) and point different clients (Cursor projects, Claude.ai connections, etc.) at specific subsets.

## Goals

- Allow users to create multiple named MCP servers, each with its own UUID-based URL and API key.
- Workflows are assigned to servers independently via the MCP Panel UI.
- The existing single-server flow (`/api/mcp/sse`) is fully preserved — users who don't need clustering are unaffected.
- Claude.ai OAuth works on named servers too (not just API key).
- Unit tests cover all new paths.
- Documentation updated via heym-documentation skill.

## Non-Goals

- Migrating existing users away from the default single-server endpoint.
- Workflow-editor-level server assignment (UI is in MCP Panel only).
- Team/workspace-level MCP clustering (out of scope).

---

## Data Model

### New table: `mcp_servers`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Used in endpoint URL |
| `user_id` | UUID FK → users | Owner |
| `name` | String(100) | User-chosen label, e.g. "CRM Tools" |
| `api_key` | String(64), unique, indexed | Per-server auth key, auto-generated on create |
| `created_at` | DateTime | |

### New table: `mcp_server_workflows` (join)

| Column | Type | Notes |
|--------|------|-------|
| `mcp_server_id` | UUID FK → mcp_servers | CASCADE DELETE |
| `workflow_id` | UUID FK → workflows | |
| composite PK | (mcp_server_id, workflow_id) | |

### Existing models — unchanged

- `User.mcp_api_key` — default server auth key, stays.
- `Workflow.mcp_enabled` — default server toggle, stays.
- `WorkflowShare.mcp_enabled` — default server shared workflow toggle, stays.

A workflow assigned to a named server does **not** require `mcp_enabled=True` — join table membership is sufficient.

---

## API Endpoints

### New router prefix: `/api/mcp/servers`

Registered alongside the existing `/api/mcp` router.

**CRUD:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mcp/servers` | List all named servers for authenticated user |
| POST | `/api/mcp/servers` | Create server (`{name}` body), returns server + api_key |
| DELETE | `/api/mcp/servers/{server_id}` | Delete server and cascade join rows |
| POST | `/api/mcp/servers/{server_id}/regenerate-key` | Replace api_key |
| PATCH | `/api/mcp/servers/{server_id}/workflows/{workflow_id}` | Toggle workflow membership (`{enabled: bool}`) |

**MCP Protocol (per named server):**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mcp/servers/{server_id}/sse` | SSE — issues session token for this server |
| POST | `/api/mcp/servers/{server_id}/message` | JSON-RPC 2.0: `tools/list`, `tools/call`, `initialize` |
| GET | `/api/mcp/servers/{server_id}/tools` | REST tool list |

### Existing endpoints — unchanged

`/api/mcp/sse`, `/api/mcp/message`, `/api/mcp/tools`, `/api/mcp/config`, `/api/mcp/regenerate-key`, `/api/mcp/workflows/{id}` — all stay as-is.

---

## Authentication

New dependency `get_named_mcp_server(server_id, ...)` resolves the calling identity:

1. **API key** — matched against `MCPServer.api_key` (not `User.mcp_api_key`).
2. **Session token** — resolved to `(user_id, server_id)` pair (see Session Management).
3. **OAuth Bearer** — validates user JWT; `server_id` comes from path param. Checks server belongs to that user.

Cross-user access is rejected: if `MCPServer.user_id ≠ authenticated user_id`, return 403.

---

## Session Management

`MCPSessionStore` extended to carry an optional `server_id`:

```python
# Before
store.create(user_id: str) → token
store.resolve(token) → user_id | None

# After (backward-compatible)
store.create(user_id: str, server_id: str | None = None) → token
store.resolve(token) → (user_id, server_id | None) | None
```

Named server SSE handler calls `store.create(user_id, server_id=str(server.id))`.
Default server SSE handler calls `store.create(user_id)` — no change.
`/api/mcp/message` resolves token; if `server_id` is present it routes to named-server logic, otherwise to default-server logic.

---

## Execution Logic

Named server tool execution reuses the existing `execute_workflow` + `_add_mcp_workflow_trace` infrastructure.
The only difference: the workflow list fed into tool lookup comes from the `mcp_server_workflows` join table instead of `Workflow.mcp_enabled`.

`trigger_source="MCP"` and LLMTrace recording are unchanged.

---

## Frontend

### MCPPanel.vue additions

A new "Named Servers" section is appended below the existing single-server UI. The existing "API Key" and "Claude" tabs are untouched.

**Server list row:** name, truncated UUID, "Copy URL" button, delete button.
**Expanded server:** SSE URL, API key (masked, copy, show/hide), "Add to Cursor" snippet, Claude config snippet, workflow assignment grid (all user workflows with per-row toggle).

### New API client methods (`api.ts` → `mcpServersApi`)

```ts
list(): Promise<MCPServerItem[]>
create(name: string): Promise<MCPServerItem>
delete(serverId: string): Promise<void>
regenerateKey(serverId: string): Promise<{ api_key: string }>
toggleWorkflow(serverId: string, workflowId: string, enabled: boolean): Promise<void>
```

### New TypeScript types

```ts
interface MCPServerItem {
  id: string
  name: string
  api_key: string
  created_at: string
  workflow_ids: string[]
}
```

---

## Unit Tests (`backend/tests/test_mcp_servers.py`)

| Test | Coverage |
|------|----------|
| `test_create_server` | Server created, api_key auto-generated, belongs to user |
| `test_list_servers` | User only sees own servers |
| `test_delete_server` | Server deleted, join rows cascade |
| `test_toggle_workflow_add` | Join row created |
| `test_toggle_workflow_remove` | Join row deleted |
| `test_tools_list_per_server` | Only assigned workflows returned as tools |
| `test_auth_wrong_key` | Wrong api_key → 403 |
| `test_auth_cross_user` | Other user's server_id → 403 |
| `test_session_token_carries_server_id` | SSE token resolves to correct (user_id, server_id) |
| `test_default_server_unaffected` | `/api/mcp/sse` still uses User.mcp_api_key, unaffected |

---

## Migration

New Alembic migration:
- Create `mcp_servers` table.
- Create `mcp_server_workflows` join table with FK cascade on `mcp_server_id`.
- No changes to existing columns.

---

## Documentation

Update via `heym-documentation` skill after implementation:
- MCP overview page: add "Named MCP Servers" section.
- New server creation flow, URL format, per-server API key usage.
