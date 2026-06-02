# Traces "Steps" Timeline — Design Spec

**Date:** 2026-05-30
**Status:** Approved (design), pending implementation plan
**Area:** `frontend/src/components/Traces/` (frontend-only; no backend changes)

## Problem

The trace detail dialog shows the LLM request and response as two raw JSON blobs.
A trace is actually a top-to-bottom **chain of steps** (system prompt → user message →
assistant reasoning → tool call → tool result → final answer), but that chain is buried
inside the JSON. Users have to mentally parse JSON to understand "what happened first,
then what happened next."

## Goal

Render the trace as a readable, vertical **Steps timeline** — "now this happened, then
that happened" — placed directly above the existing raw JSON. Each step is a collapsible
card. The raw Request/Response JSON blocks are **kept**, unchanged, at the bottom of the
panel.

This is a **frontend-only** change. All required data already exists in the trace's
`request` and `response` objects; no new API fields or backend changes are needed.

## Data sources (already present)

For conversation traces (`request_type` in `chat.completions`, `chat.completions.stream`,
`batches.chat.completions`):

- **`request.messages[]`** — ordered conversation. Each entry has `role`
  (`system` | `user` | `assistant` | `tool`) and `content`. An `assistant` entry may carry
  `tool_calls: [{ id, type, function: { name, arguments(JSON string) } }]`. A `tool` entry
  carries the tool result `content` and a `tool_call_id`.
- **`request.tools[]`** — tool definitions (not rendered as steps).
- **`request.skills_included[]`** — optional; already rendered in the existing "Skills
  Included" section (unchanged).
- **`response.text`** — the final assistant answer (NOT present in `messages`).
- **`response.tool_calls[]`** — enriched, collected tool executions:
  `{ name, arguments(object), result, elapsed_ms?, source?("mcp"|"skill"|...), mcp_server? }`.
  Used to enrich tool steps with duration, source badge, and result.
- **`response.usage`** (`prompt_tokens`/`completion_tokens`/`total_tokens`),
  **`response.elapsed_ms`**, **`response.error`**.

For non-conversation traces (no `request.messages`): there is no chain, only an input dict
and an output dict.

## Layout (trace detail dialog, top → bottom)

Order inside the existing detail `<Dialog>` in `TracesPanel.vue`:

1. Summary stat cards (Status / Model / Time / Tokens) — **kept**
2. `TraceDurationChart` ("Duration Breakdown") — **kept**
3. Meta cards (Created At / Credential / Workflow-Node) + Error + "Skills Included" — **kept**
4. "Tool Calls" list — **kept** (explicitly NOT removed)
5. 🆕 **Steps timeline** — placed **immediately above the Request block**
6. Request (full raw JSON `<pre>`) — **kept**, stays at the bottom
7. Response (full raw JSON `<pre>`) — **kept**, stays at the bottom

No existing section is deleted. The timeline is additive and sits as a readable preview
directly before the raw JSON.

## Component architecture

`TracesPanel.vue` is already ~1076 lines (well over the 300-line guideline). The new
feature is extracted into focused, independently testable units instead of growing the file:

- **`frontend/src/lib/traceSteps.ts`** — pure, side-effect-free parser:
  `export function buildTraceSteps(trace: LLMTraceDetail): TraceStep[]`.
  Plus the exported `TraceStep` type. No Vue imports. Unit-testable.
- **`frontend/src/components/Traces/TraceStepsTimeline.vue`** — presentational; props:
  `{ steps: TraceStep[] }`. Renders the vertical list + connector line. Owns the per-step
  expand/collapse state (e.g. a `Set<string>` of open step ids).
- **`frontend/src/components/Traces/TraceStepCard.vue`** — a single collapsible step card:
  header (icon + role label + summary + optional duration/tokens/badges + chevron) and, when
  open, the readable detail followed by the auto-shown raw JSON fragment for that step.

`TracesPanel.vue` change is minimal: compute `steps = buildTraceSteps(selectedTrace)` and
render `<TraceStepsTimeline :steps="steps" />` immediately above the Request block.

**Markdown rendering:** the frontend has no shared markdown helper today — each component
(e.g. `ChatConversation.vue`) defines its own `renderMarkdown(content)` using
`marked(content, { breaks: true, gfm: true })` piped through `DOMPurify.sanitize(...)`.
To avoid copy-pasting that into the new components, add a small shared
`frontend/src/lib/markdown.ts` exporting `renderMarkdown(content: string): string` (same
marked + DOMPurify config) and use it in `TraceStepCard.vue`. Existing components are NOT
refactored to use it (out of scope); the shared helper is introduced only for the new code.

## Step model

```ts
type TraceStepKind =
  | "system" | "user" | "assistant" | "tool" | "answer"  // conversation traces
  | "request" | "response";                              // non-conversation fallback

interface TraceStepBadge { label: string }                // e.g. "MCP: fetch", "Skill"

interface TraceStep {
  id: string;                 // stable key (e.g. "msg-2", "tool-eb0e6f771", "answer")
  kind: TraceStepKind;
  icon: "system" | "user" | "assistant" | "tool" | "answer" | "request" | "response";
  roleLabel: string;          // ENGLISH label (see i18n note)
  summary: string;            // one-line plain-text summary, truncated for the header
  detail?: string;            // full readable text (content / arguments / result)
  detailIsMarkdown?: boolean; // true for assistant content + final answer
  json: unknown;              // the raw JSON fragment for THIS step (auto-shown on expand)
  durationMs?: number;        // tool elapsed_ms, or response.elapsed_ms for the answer
  tokens?: number;            // total_tokens on the answer step
  badges?: TraceStepBadge[];  // MCP / Skill source markers on tool steps
}
```

## Parser rules — `buildTraceSteps(trace)`

**Conversation traces** (`Array.isArray(request.messages)` and non-empty):

1. Walk `request.messages` in order:
   - `role: "system"` → step `kind:"system"`, label **"System"**, summary = first line of
     content (truncated), `json` = the message object.
   - `role: "user"` → step `kind:"user"`, label **"User"**, summary = content (truncated),
     `json` = the message object.
   - `role: "assistant"`:
     - If it has text `content`, emit an `kind:"assistant"` step, label **"Assistant"**,
       summary = content (truncated), `detailIsMarkdown: true`, `json` = the message object.
       (If content is empty but it has `tool_calls`, skip the standalone assistant step and
       go straight to the tool steps to avoid an empty card.)
     - For each entry in `tool_calls`, emit a `kind:"tool"` step (see enrichment below).
   - `role: "tool"` → this is a tool **result**; do not emit a standalone step. Attach its
     `content` as the `result`/`detail` of the matching tool step (match by `tool_call_id`).
2. **Tool step enrichment:** for each assistant `tool_calls[i]`, build a tool step:
   - label **"Tool · {name}"**, icon `tool`.
   - `arguments`: parse the JSON-string `function.arguments` to an object for the readable
     detail; keep the raw form in `json`.
   - Match to `response.tool_calls[]` to enrich: by `tool_call_id`/`id` if available, else by
     `name` + deep-equal `arguments`, else by positional order. From the match take
     `result`, `elapsed_ms` (→ `durationMs`), and `source`/`mcp_server` (→ badges:
     `source === "mcp"` ⇒ `"MCP" + (mcp_server ? ": " + mcp_server : "")`;
     `source === "skill"` ⇒ `"Skill"`).
   - `result` precedence: matching `role:"tool"` message content, else matched
     `response.tool_calls[].result`.
   - `json` = `{ ...the assistant tool_call entry, ...matched response.tool_calls entry }`
     (the per-call slice, so the step's JSON is self-contained).
3. **Final answer:** if `response.text` is a non-empty string, append a `kind:"answer"`
   step, label **"Answer"**, summary = first line/sentence of the text (truncated),
   `detailIsMarkdown: true`, `durationMs = response.elapsed_ms`,
   `tokens = response.usage?.total_tokens`, `json` = a compact slice of the response
   (`text`, `model`, `usage`, `elapsed_ms`) — NOT the full `tool_calls` array (those are
   already their own steps).
4. **Error:** if `response.error` (or `trace.error`) is set, the answer step is marked as an
   error variant (destructive styling) and shows the error text as its detail. The existing
   top-level error banner is unchanged.

**Non-conversation traces** (no usable `messages`) — minimal 2-step timeline (per decision B):

- Step `kind:"request"`, label **"Request"**, icon `request`, summary = a short descriptor
  (e.g. the `request_type`), `json` = the full `request` object.
- Step `kind:"response"`, label **"Response"**, icon `response`, summary = short status
  (e.g. `"success"`/`"error"` or first line of any `text`), `durationMs = response.elapsed_ms`
  if present, `json` = the full `response` object.

**Empty/edge:** if both `request` and `response` are empty/absent, `buildTraceSteps` returns
`[]` and the timeline section does not render (raw JSON blocks still show as today).

## Step card behavior

- **Collapsed (default):** icon + role label + one-line summary + (optional) duration /
  tokens / source badges + a `▸` chevron. This is the clean "story" overview.
- **Expanded (on header click):** chevron flips to `▾`; body shows:
  1. **Readable detail** first — full content / arguments / result. For `assistant` and
     `answer` steps render `detail` as markdown; for tool steps show arguments as key/value
     and the result text.
  2. **Raw JSON fragment** for that step, **shown automatically** (no extra "show" toggle),
     pretty-printed via the existing `formatJson` helper in a `<pre>` consistent with the
     current JSON blocks.
- Expand/collapse state lives in `TraceStepsTimeline.vue` (multiple steps may be open at
  once). State resets when the selected trace changes.

## Visual style

Matches the existing dialog: `Card`/muted surfaces, `lucide-vue-next` icons, Tailwind
classes already used in `TracesPanel.vue`. Icon mapping (lucide): system → `Settings`/`Cog`,
user → `User`, assistant → `Bot`, tool → `Wrench`, answer → `CheckCircle`/`Sparkles`,
request → `ArrowUpRight`, response → `ArrowDownLeft` (final choices finalized during
implementation to match the existing icon set). Source badges reuse the existing badge
styling (`bg-primary/20 text-primary dark:bg-primary/25 dark:text-accent-foreground`).
Vertical connector line between step dots conveys ordering.

## i18n / language constraint

AGENTS.md forbids Turkish text in code/comments. All rendered labels are **English**
("System", "User", "Assistant", "Tool · {name}", "Answer", "Request", "Response"),
consistent with the rest of the Traces UI ("Request", "Response", "Tool Calls", "Duration
Breakdown", "Skills Included"). The Turkish mockups produced during brainstorming were for
discussion only.

## Testing

The parser is the testable core. Vitest 3.2.4 is already a dependency but the frontend has
no test runner wired up yet (no `test` script, no config, no test files).

- Add a minimal `vitest.config.ts` (or extend `vite.config.ts` with a `test` block) and a
  `"test": "vitest run"` script in `frontend/package.json`. This establishes the frontend
  test harness with the smallest possible footprint.
- Add `frontend/src/lib/traceSteps.test.ts` covering:
  - The Fenerbahçe-style trace: system + user + assistant(with tool_call) + answer, with a
    matched `response.tool_calls` entry → correct ordered steps, MCP badge, duration on the
    tool step, tokens/duration on the answer.
  - A `tool` result message matched to its tool step by `tool_call_id`.
  - A multi-tool / multi-iteration trace (tool calls matched by order when ids are absent).
  - A non-conversation trace (`images.generate`) → exactly two steps (Request, Response).
  - Empty request+response → `[]`.
- `bun run lint` and `bun run typecheck` must pass (strict mode: explicit return types,
  `interface` over `type` for objects, no unused locals, `_`-prefixed unused params).

## Documentation

Medium UI feature → update docs via the `heym-documentation` skill (Traces section: describe
the Steps timeline, expand/collapse, and that raw JSON remains available below).

## Out of scope

- Backend changes or new API fields.
- Streaming / live-updating timeline while a call is in progress.
- Re-rendering or restructuring the existing Duration Breakdown, Tool Calls, Skills, or JSON
  sections (only the new timeline is added; order is adjusted only to place it above Request).
- A JSON ↔ Steps toggle (both are always shown; timeline above, JSON below).
