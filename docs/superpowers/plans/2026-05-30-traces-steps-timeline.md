# Traces "Steps" Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a readable, vertical "Steps" timeline to the trace detail dialog that renders the trace as an ordered chain (system → user → assistant → tool → answer) directly above the existing raw Request/Response JSON, which is kept unchanged.

**Architecture:** Frontend-only. A pure parser (`lib/traceSteps.ts`) turns a `LLMTraceDetail` into `TraceStep[]` from data already present in `request.messages` + `response.tool_calls` + `response.text`. Two presentational Vue components (`TraceStepsTimeline.vue`, `TraceStepCard.vue`) render the steps with per-step expand/collapse; an expanded step shows a readable detail and the step's raw JSON fragment automatically. `TracesPanel.vue` is touched minimally to render the timeline above the Request block. No backend/API changes.

**Tech Stack:** Vue 3 `<script setup>` + TypeScript (strict) + Tailwind, `lucide-vue-next` icons, `marked` + `dompurify` for markdown, Vitest for the parser unit test.

**Spec:** `docs/superpowers/specs/2026-05-30-traces-steps-timeline-design.md`

> **UPDATE 2026-05-31 (per user request): no frontend tests.** Task 1 (Vitest harness)
> is dropped, and `traceSteps.test.ts` is not written. The parser is verified via
> `bun run typecheck` + manual smoke. The `buildTraceSteps` implementation in Task 3 is
> unchanged; only its test steps are skipped.

---

## File Structure

- Create `frontend/vitest.config.ts` — wires Vitest with the `@` alias (node environment).
- Modify `frontend/package.json` — add `"test": "vitest run"` script.
- Create `frontend/src/lib/markdown.ts` — shared `renderMarkdown(content)` (marked + DOMPurify).
- Create `frontend/src/lib/traceSteps.ts` — `TraceStep` type + `buildTraceSteps(trace)` parser.
- Create `frontend/src/lib/traceSteps.test.ts` — Vitest unit tests for the parser.
- Create `frontend/src/components/Traces/TraceStepCard.vue` — single collapsible step card.
- Create `frontend/src/components/Traces/TraceStepsTimeline.vue` — vertical list of step cards.
- Modify `frontend/src/components/Traces/TracesPanel.vue` — import + computed + render above Request.

All commands below assume the working directory `frontend/` unless noted. Run from the repo root with `cd frontend && …`.

---

### Task 1: Wire up the Vitest harness

**Files:**
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/package.json` (scripts block)

- [ ] **Step 1: Create the Vitest config**

Create `frontend/vitest.config.ts`:

```ts
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

- [ ] **Step 2: Add the `test` script**

In `frontend/package.json`, add a `test` script to the `"scripts"` block so it reads:

```json
  "scripts": {
    "dev": "vite --port 4017",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "lint": "node ./scripts/run-eslint.mjs . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx,.cts,.mts --fix",
    "typecheck": "vue-tsc --noEmit",
    "test": "vitest run"
  },
```

- [ ] **Step 3: Verify the harness runs**

Run: `cd frontend && bun run test --passWithNoTests`
Expected: Vitest starts, reports **"No test files found"**, and exits **0** (the `--passWithNoTests` flag is passed only for this one-off wiring check; it is intentionally NOT baked into the `package.json` script). This proves the harness is wired. (If it errors about a missing `vitest` binary, run `bun install` first.)

- [ ] **Step 4: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/vitest.config.ts frontend/package.json
git commit -m "chore(frontend): wire up vitest harness

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Shared markdown helper

**Files:**
- Create: `frontend/src/lib/markdown.ts`

- [ ] **Step 1: Create the helper**

Create `frontend/src/lib/markdown.ts` (mirrors the existing per-component `renderMarkdown` in `ChatConversation.vue`):

```ts
import DOMPurify from "dompurify";
import { marked } from "marked";

const ALLOWED_TAGS = [
  "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
  "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "hr",
  "table", "thead", "tbody", "tr", "th", "td", "img", "video", "source",
];

const ALLOWED_ATTR = [
  "href", "target", "rel", "src", "alt", "controls", "playsinline",
  "muted", "loop", "preload", "type", "style",
];

/** Render trusted-but-sanitized markdown to an HTML string for v-html. */
export function renderMarkdown(content: string): string {
  if (!content) return "";
  const html = marked(content, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && bun run typecheck`
Expected: PASS (no errors).

- [ ] **Step 3: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/src/lib/markdown.ts
git commit -m "feat(frontend): add shared renderMarkdown helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Trace steps parser (`lib/traceSteps.ts`) — TDD

**Files:**
- Create: `frontend/src/lib/traceSteps.ts`
- Test: `frontend/src/lib/traceSteps.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/traceSteps.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import type { LLMTraceDetail } from "@/types/trace";
import { buildTraceSteps } from "@/lib/traceSteps";

function makeTrace(partial: Partial<LLMTraceDetail>): LLMTraceDetail {
  return {
    id: "t1",
    created_at: "2026-05-30T00:00:00Z",
    source: "assistant",
    request_type: "chat.completions",
    provider: "openai",
    model: "zai-glm-4.7",
    credential_id: null,
    credential_name: null,
    workflow_id: null,
    workflow_name: null,
    node_id: null,
    node_label: null,
    status: "success",
    elapsed_ms: 17391.62,
    prompt_tokens: 3492,
    completion_tokens: 1264,
    total_tokens: 4756,
    cost_usd: null,
    is_priced: false,
    request: {},
    response: {},
    error: null,
    ...partial,
  };
}

describe("buildTraceSteps", () => {
  it("builds an ordered timeline for system+user+assistant(tool)+answer", () => {
    const trace = makeTrace({
      request: {
        messages: [
          { role: "system", content: "You are a web research assistant." },
          { role: "user", content: "fenerbahce ne zaman sampiyon oldu ?" },
          {
            role: "assistant",
            content: "Researching championship dates.",
            tool_calls: [
              {
                id: "eb0e6f771",
                type: "function",
                function: { name: "fetch", arguments: '{"url":"https://tr.wikipedia.org/wiki/x"}' },
              },
            ],
          },
        ],
      },
      response: {
        text: "**Fenerbahce** has 19 league titles.",
        model: "zai-glm-4.7",
        usage: { prompt_tokens: 3492, completion_tokens: 1264, total_tokens: 4756 },
        elapsed_ms: 17391.62,
        tool_calls: [
          {
            name: "fetch",
            arguments: { url: "https://tr.wikipedia.org/wiki/x" },
            result: "Wikipedia content...",
            elapsed_ms: 17391.62,
            source: "mcp",
            mcp_server: "fetch",
          },
        ],
      },
    });

    const steps = buildTraceSteps(trace);
    expect(steps.map((s) => s.kind)).toEqual(["system", "user", "assistant", "tool", "answer"]);

    const tool = steps[3];
    expect(tool.roleLabel).toBe("Tool · fetch");
    expect(tool.durationMs).toBe(17391.62);
    expect(tool.badges).toEqual([{ label: "MCP: fetch" }]);
    expect(tool.resultText).toContain("Wikipedia content");

    const answer = steps[4];
    expect(answer.kind).toBe("answer");
    expect(answer.tokens).toBe(4756);
    expect(answer.durationMs).toBe(17391.62);
    expect(answer.detailIsMarkdown).toBe(true);
  });

  it("attaches a tool-result message to its tool step via tool_call_id", () => {
    const trace = makeTrace({
      request: {
        messages: [
          { role: "user", content: "hi" },
          {
            role: "assistant",
            content: "",
            tool_calls: [
              { id: "call_1", type: "function", function: { name: "lookup", arguments: "{}" } },
            ],
          },
          { role: "tool", tool_call_id: "call_1", content: "RESULT FROM MESSAGE" },
        ],
      },
      response: { text: "done", elapsed_ms: 10 },
    });

    const steps = buildTraceSteps(trace);
    // assistant content is empty -> no standalone assistant step
    expect(steps.map((s) => s.kind)).toEqual(["user", "tool", "answer"]);
    expect(steps[1].resultText).toContain("RESULT FROM MESSAGE");
  });

  it("matches response tool_calls positionally when ids are absent", () => {
    const trace = makeTrace({
      request: {
        messages: [
          { role: "user", content: "go" },
          {
            role: "assistant",
            content: "",
            tool_calls: [
              { type: "function", function: { name: "a", arguments: "{}" } },
              { type: "function", function: { name: "b", arguments: "{}" } },
            ],
          },
        ],
      },
      response: {
        text: "ok",
        tool_calls: [
          { name: "a", result: "ra", elapsed_ms: 5 },
          { name: "b", result: "rb", elapsed_ms: 7 },
        ],
      },
    });

    const steps = buildTraceSteps(trace);
    const tools = steps.filter((s) => s.kind === "tool");
    expect(tools).toHaveLength(2);
    expect(tools[0].durationMs).toBe(5);
    expect(tools[1].durationMs).toBe(7);
    expect(tools[1].resultText).toContain("rb");
  });

  it("builds a minimal Request/Response timeline for non-conversation traces", () => {
    const trace = makeTrace({
      request_type: "images.generate",
      request: { prompt: "a cat", size: "1024x1024" },
      response: { url: "https://img/x.png", elapsed_ms: 2200 },
    });

    const steps = buildTraceSteps(trace);
    expect(steps.map((s) => s.kind)).toEqual(["request", "response"]);
    expect(steps[0].roleLabel).toBe("Request");
    expect(steps[1].roleLabel).toBe("Response");
    expect(steps[1].durationMs).toBe(2200);
  });

  it("returns no steps when request and response are both empty", () => {
    const trace = makeTrace({ request: {}, response: {} });
    expect(buildTraceSteps(trace)).toEqual([]);
  });

  it("marks the answer step as an error when response.error is set", () => {
    const trace = makeTrace({
      status: "error",
      request: { messages: [{ role: "user", content: "x" }] },
      response: { text: "", error: "rate limited", elapsed_ms: 12 },
      error: "rate limited",
    });

    const steps = buildTraceSteps(trace);
    const answer = steps[steps.length - 1];
    expect(answer.kind).toBe("answer");
    expect(answer.isError).toBe(true);
    expect(answer.detail).toContain("rate limited");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && bun run test`
Expected: FAIL — Vitest cannot resolve `@/lib/traceSteps` ("Failed to load … traceSteps" / module not found), because the file does not exist yet.

- [ ] **Step 3: Implement the parser**

Create `frontend/src/lib/traceSteps.ts`:

```ts
import type { LLMTraceDetail } from "@/types/trace";

export type TraceStepKind =
  | "system"
  | "user"
  | "assistant"
  | "tool"
  | "answer"
  | "request"
  | "response";

export interface TraceStepBadge {
  label: string;
}

export interface TraceStep {
  id: string;
  kind: TraceStepKind;
  icon: TraceStepKind;
  roleLabel: string;
  summary: string;
  detail?: string;
  detailIsMarkdown?: boolean;
  argumentsText?: string;
  resultText?: string;
  json: unknown;
  durationMs?: number;
  tokens?: number;
  isError?: boolean;
  badges?: TraceStepBadge[];
}

interface RawToolCall {
  id?: string;
  type?: string;
  function?: { name?: string; arguments?: string };
}

interface RawMessage {
  role?: string;
  content?: unknown;
  tool_calls?: RawToolCall[];
  tool_call_id?: string;
}

interface RawResponseToolCall {
  id?: string;
  tool_call_id?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
  elapsed_ms?: number;
  source?: string;
  mcp_server?: string;
}

const SUMMARY_MAX = 140;
const ARGS_SUMMARY_MAX = 80;

function asText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          const text = (part as { text?: unknown }).text;
          return typeof text === "string" ? text : "";
        }
        return "";
      })
      .join(" ")
      .trim();
  }
  if (content == null) return "";
  return safeStringify(content);
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function summarize(text: string, max = SUMMARY_MAX): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (collapsed.length <= max) return collapsed;
  return `${collapsed.slice(0, max - 1).trimEnd()}…`;
}

function buildToolStep(
  msgIndex: number,
  tcIndex: number,
  rawCall: RawToolCall,
  enriched: RawResponseToolCall | undefined,
  toolResultById: Map<string, RawMessage>,
): TraceStep {
  const name = rawCall.function?.name ?? "tool";
  const argsRaw = rawCall.function?.arguments;

  let argsObj: unknown;
  if (typeof argsRaw === "string" && argsRaw.length > 0) {
    try {
      argsObj = JSON.parse(argsRaw);
    } catch {
      argsObj = argsRaw;
    }
  } else if (enriched?.arguments !== undefined) {
    argsObj = enriched.arguments;
  }

  let resultValue: unknown;
  const id = rawCall.id;
  if (id && toolResultById.has(id)) {
    resultValue = toolResultById.get(id)?.content;
  } else if (enriched?.result !== undefined) {
    resultValue = enriched.result;
  }

  const badges: TraceStepBadge[] = [];
  if (enriched?.source === "mcp") {
    badges.push({ label: enriched.mcp_server ? `MCP: ${enriched.mcp_server}` : "MCP" });
  } else if (enriched?.source === "skill") {
    badges.push({ label: "Skill" });
  }

  const argsCompact =
    argsObj === undefined ? "" : typeof argsObj === "string" ? argsObj : safeJsonCompact(argsObj);
  const argumentsText =
    argsObj === undefined ? undefined : typeof argsObj === "string" ? argsObj : safeStringify(argsObj);
  const resultText =
    resultValue === undefined
      ? undefined
      : typeof resultValue === "string"
        ? resultValue
        : safeStringify(resultValue);

  return {
    id: id ? `tool-${id}` : `tool-${msgIndex}-${tcIndex}`,
    kind: "tool",
    icon: "tool",
    roleLabel: `Tool · ${name}`,
    summary: argsCompact ? `${name}(${summarize(argsCompact, ARGS_SUMMARY_MAX)})` : `${name}()`,
    argumentsText,
    resultText,
    json: {
      ...(rawCall as Record<string, unknown>),
      ...(enriched ? { _response: enriched } : {}),
      ...(resultValue !== undefined ? { result: resultValue } : {}),
    },
    durationMs: typeof enriched?.elapsed_ms === "number" ? enriched.elapsed_ms : undefined,
    badges: badges.length > 0 ? badges : undefined,
  };
}

function safeJsonCompact(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function buildConversationSteps(
  messages: RawMessage[],
  response: Record<string, unknown>,
  trace: LLMTraceDetail,
): TraceStep[] {
  const steps: TraceStep[] = [];

  const toolResultById = new Map<string, RawMessage>();
  for (const msg of messages) {
    if (msg.role === "tool" && typeof msg.tool_call_id === "string") {
      toolResultById.set(msg.tool_call_id, msg);
    }
  }

  const pool = Array.isArray(response.tool_calls)
    ? (response.tool_calls as RawResponseToolCall[]).map((tc) => ({ tc, used: false }))
    : [];

  function matchResponseToolCall(
    name: string,
    id: string | undefined,
  ): RawResponseToolCall | undefined {
    if (id) {
      const byId = pool.find((e) => !e.used && (e.tc.id === id || e.tc.tool_call_id === id));
      if (byId) {
        byId.used = true;
        return byId.tc;
      }
    }
    const byName = pool.find((e) => !e.used && e.tc.name === name);
    if (byName) {
      byName.used = true;
      return byName.tc;
    }
    const next = pool.find((e) => !e.used);
    if (next) {
      next.used = true;
      return next.tc;
    }
    return undefined;
  }

  messages.forEach((msg, index) => {
    if (msg.role === "system") {
      const text = asText(msg.content);
      steps.push({
        id: `msg-${index}`,
        kind: "system",
        icon: "system",
        roleLabel: "System",
        summary: summarize(text) || "System instructions",
        detail: text,
        json: msg,
      });
    } else if (msg.role === "user") {
      const text = asText(msg.content);
      steps.push({
        id: `msg-${index}`,
        kind: "user",
        icon: "user",
        roleLabel: "User",
        summary: summarize(text),
        detail: text,
        json: msg,
      });
    } else if (msg.role === "assistant") {
      const text = asText(msg.content);
      if (text) {
        steps.push({
          id: `msg-${index}`,
          kind: "assistant",
          icon: "assistant",
          roleLabel: "Assistant",
          summary: summarize(text),
          detail: text,
          detailIsMarkdown: true,
          json: { role: msg.role, content: msg.content },
        });
      }
      const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
      toolCalls.forEach((tc, tcIndex) => {
        const enriched = matchResponseToolCall(tc.function?.name ?? "tool", tc.id);
        steps.push(buildToolStep(index, tcIndex, tc, enriched, toolResultById));
      });
    }
    // msg.role === "tool" is consumed as a tool step's result above.
  });

  const text = typeof response.text === "string" ? response.text : "";
  const error =
    (typeof response.error === "string" && response.error ? response.error : null) ?? trace.error;
  if (text || error) {
    const usage = response.usage as { total_tokens?: number } | undefined;
    const elapsed = typeof response.elapsed_ms === "number" ? response.elapsed_ms : undefined;
    steps.push({
      id: "answer",
      kind: "answer",
      icon: "answer",
      roleLabel: "Answer",
      summary: error ? summarize(`Error: ${error}`) : summarize(text),
      detail: error ? error : text,
      detailIsMarkdown: !error,
      durationMs: elapsed,
      tokens: typeof usage?.total_tokens === "number" ? usage.total_tokens : undefined,
      isError: Boolean(error),
      json: {
        text: response.text,
        model: response.model,
        usage: response.usage,
        elapsed_ms: response.elapsed_ms,
        ...(error ? { error } : {}),
      },
    });
  }

  return steps;
}

function buildFallbackSteps(
  trace: LLMTraceDetail,
  request: Record<string, unknown>,
  response: Record<string, unknown>,
): TraceStep[] {
  const hasRequest = Object.keys(request).length > 0;
  const hasResponse = Object.keys(response).length > 0;
  if (!hasRequest && !hasResponse) return [];

  const steps: TraceStep[] = [];
  if (hasRequest) {
    steps.push({
      id: "request",
      kind: "request",
      icon: "request",
      roleLabel: "Request",
      summary: summarize(trace.request_type || "Request"),
      json: request,
    });
  }
  if (hasResponse) {
    const error =
      (typeof response.error === "string" && response.error ? response.error : null) ?? trace.error;
    const text = typeof response.text === "string" ? response.text : "";
    const elapsed = typeof response.elapsed_ms === "number" ? response.elapsed_ms : undefined;
    steps.push({
      id: "response",
      kind: "response",
      icon: "response",
      roleLabel: "Response",
      summary: error ? summarize(`Error: ${error}`) : text ? summarize(text) : trace.status,
      detail: text || undefined,
      detailIsMarkdown: Boolean(text) && !error,
      durationMs: elapsed,
      isError: Boolean(error),
      json: response,
    });
  }
  return steps;
}

/** Turn a trace into an ordered list of readable steps for the timeline view. */
export function buildTraceSteps(trace: LLMTraceDetail): TraceStep[] {
  const request = (trace.request ?? {}) as Record<string, unknown>;
  const response = (trace.response ?? {}) as Record<string, unknown>;
  const messages = request.messages;

  if (Array.isArray(messages) && messages.length > 0) {
    return buildConversationSteps(messages as RawMessage[], response, trace);
  }
  return buildFallbackSteps(trace, request, response);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && bun run test`
Expected: PASS — all 6 tests in `traceSteps.test.ts` green.

- [ ] **Step 5: Type-check**

Run: `cd frontend && bun run typecheck`
Expected: PASS (the `.test.ts` is covered by `src/**/*.ts`).

- [ ] **Step 6: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/src/lib/traceSteps.ts frontend/src/lib/traceSteps.test.ts
git commit -m "feat(traces): add buildTraceSteps parser with tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Step card component (`TraceStepCard.vue`)

**Files:**
- Create: `frontend/src/components/Traces/TraceStepCard.vue`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Traces/TraceStepCard.vue`:

```vue
<script setup lang="ts">
import { computed } from "vue";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Bot,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  Settings,
  User,
  Wrench,
} from "lucide-vue-next";

import type { TraceStep } from "@/lib/traceSteps";
import { renderMarkdown } from "@/lib/markdown";

const props = defineProps<{
  step: TraceStep;
  open: boolean;
}>();

const emit = defineEmits<{
  (e: "toggle"): void;
}>();

const ICONS = {
  system: Settings,
  user: User,
  assistant: Bot,
  tool: Wrench,
  answer: CircleCheck,
  request: ArrowUpRight,
  response: ArrowDownLeft,
} as const;

const iconComponent = computed(() => ICONS[props.step.icon]);

function formatStepDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${Math.round(ms)} ms`;
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

const jsonText = computed(() => formatJson(props.step.json));
</script>

<template>
  <div
    class="rounded-lg border bg-muted/20 transition-colors"
    :class="open ? 'border-primary/40' : 'border-border/50'"
  >
    <button
      type="button"
      class="flex w-full items-center gap-2 px-3 py-2 text-left"
      @click="emit('toggle')"
    >
      <span
        class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted"
        :class="step.isError ? 'text-destructive' : 'text-muted-foreground'"
      >
        <component
          :is="iconComponent"
          class="h-3.5 w-3.5"
        />
      </span>
      <span class="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {{ step.roleLabel }}
      </span>
      <span
        class="min-w-0 flex-1 truncate text-sm"
        :class="step.isError ? 'text-destructive' : ''"
      >
        {{ step.summary }}
      </span>
      <span
        v-for="(badge, i) in step.badges"
        :key="i"
        class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary dark:bg-primary/25 dark:text-accent-foreground"
      >
        {{ badge.label }}
      </span>
      <span
        v-if="step.tokens != null"
        class="shrink-0 text-[11px] text-muted-foreground tabular-nums"
      >
        {{ step.tokens }} tok
      </span>
      <span
        v-if="step.durationMs != null"
        class="shrink-0 text-[11px] text-muted-foreground tabular-nums"
      >
        {{ formatStepDuration(step.durationMs) }}
      </span>
      <component
        :is="open ? ChevronDown : ChevronRight"
        class="h-4 w-4 shrink-0 text-muted-foreground"
      />
    </button>

    <div
      v-if="open"
      class="border-t border-border/40 px-3 py-3 space-y-3"
    >
      <template v-if="step.kind === 'tool'">
        <div
          v-if="step.argumentsText"
          class="space-y-1"
        >
          <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Arguments
          </div>
          <pre class="text-xs bg-muted/40 rounded-md p-2 overflow-auto whitespace-pre-wrap">{{ step.argumentsText }}</pre>
        </div>
        <div
          v-if="step.resultText"
          class="space-y-1"
        >
          <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Result
          </div>
          <pre class="text-xs bg-muted/40 rounded-md p-2 overflow-auto whitespace-pre-wrap max-h-60">{{ step.resultText }}</pre>
        </div>
      </template>

      <div
        v-else-if="step.detail && step.detailIsMarkdown"
        class="text-sm leading-relaxed break-words [&_table]:w-full [&_table]:text-xs [&_td]:border [&_td]:border-border/40 [&_td]:px-1.5 [&_td]:py-0.5 [&_th]:px-1.5 [&_th]:py-0.5 [&_a]:text-primary [&_a]:underline [&_pre]:bg-muted/40 [&_pre]:p-2 [&_pre]:rounded [&_pre]:overflow-auto"
        v-html="renderMarkdown(step.detail)"
      />

      <div
        v-else-if="step.detail"
        class="text-sm whitespace-pre-wrap break-words"
      >
        {{ step.detail }}
      </div>

      <div class="space-y-1">
        <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Raw JSON
        </div>
        <pre class="text-xs bg-muted/30 border rounded-md p-2 overflow-auto max-h-72 whitespace-pre-wrap">{{ jsonText }}</pre>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Verify lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS. (`v-html` is already used elsewhere — e.g. `ChatConversation.vue` — so the lint config permits it.)

- [ ] **Step 3: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/src/components/Traces/TraceStepCard.vue
git commit -m "feat(traces): add TraceStepCard component

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Timeline list component (`TraceStepsTimeline.vue`)

**Files:**
- Create: `frontend/src/components/Traces/TraceStepsTimeline.vue`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Traces/TraceStepsTimeline.vue`:

```vue
<script setup lang="ts">
import { ref, watch } from "vue";

import type { TraceStep } from "@/lib/traceSteps";

import TraceStepCard from "@/components/Traces/TraceStepCard.vue";

const props = defineProps<{
  steps: TraceStep[];
}>();

const openIds = ref<Set<string>>(new Set());

function toggle(id: string): void {
  const next = new Set(openIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  openIds.value = next;
}

// Collapse everything when the step set changes (navigating between traces).
watch(
  () => props.steps,
  () => {
    openIds.value = new Set();
  },
);
</script>

<template>
  <div class="space-y-2">
    <div class="text-sm font-medium">
      Steps
    </div>
    <div class="space-y-2">
      <TraceStepCard
        v-for="step in steps"
        :key="step.id"
        :step="step"
        :open="openIds.has(step.id)"
        @toggle="toggle(step.id)"
      />
    </div>
  </div>
</template>
```

- [ ] **Step 2: Verify lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/src/components/Traces/TraceStepsTimeline.vue
git commit -m "feat(traces): add TraceStepsTimeline component

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Integrate the timeline into `TracesPanel.vue`

**Files:**
- Modify: `frontend/src/components/Traces/TracesPanel.vue`

- [ ] **Step 1: Add the component import**

In `frontend/src/components/Traces/TracesPanel.vue`, find:

```ts
import TracesTimeRangeSelect from "@/components/Traces/TracesTimeRangeSelect.vue";
```

Add immediately after it:

```ts
import TraceStepsTimeline from "@/components/Traces/TraceStepsTimeline.vue";
```

- [ ] **Step 2: Add the parser import**

Find:

```ts
import { credentialsApi, traceApi, workflowApi } from "@/services/api";
```

Add immediately after it:

```ts
import { buildTraceSteps, type TraceStep } from "@/lib/traceSteps";
```

- [ ] **Step 3: Add the `steps` computed**

Find the existing `spans` computed:

```ts
const spans = computed(() =>
  selectedTrace.value ? buildTraceSpans(selectedTrace.value) : []
);
```

Add immediately after it:

```ts
const steps = computed<TraceStep[]>(() =>
  selectedTrace.value ? buildTraceSteps(selectedTrace.value) : [],
);
```

- [ ] **Step 4: Render the timeline above the Request block**

Find the Request block opening (unique because of the "Request" label):

```html
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="text-sm font-medium">
              Request
            </div>
```

Insert this immediately before it (so the timeline renders just above Request):

```html
        <TraceStepsTimeline
          v-if="steps.length > 0"
          :steps="steps"
        />

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="text-sm font-medium">
              Request
            </div>
```

- [ ] **Step 5: Verify lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add frontend/src/components/Traces/TracesPanel.vue
git commit -m "feat(traces): render Steps timeline above raw JSON in trace detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend gate**

Run:

```bash
cd /Users/mbakgun/Projects/heym/heymrun/frontend && bun run lint && bun run typecheck && bun run test && bun run build
```

Expected: lint PASS, typecheck PASS, all parser tests PASS, production build succeeds.

- [ ] **Step 2: Manual smoke check (optional but recommended)**

Start the app (`./run.sh` from repo root), open **Traces**, click a `chat.completions` trace that used a tool. Confirm:
- A **Steps** section appears directly above the **Request** JSON block.
- Steps read top-to-bottom: System → User → Assistant → Tool · … → Answer.
- Clicking a step expands it: readable detail first, then the step's raw JSON (auto-shown).
- Tool steps show a duration and an MCP/Skill badge where applicable.
- The original **Tool Calls** list and **Request/Response** JSON blocks are still present, with JSON at the bottom.
- Open a non-conversation trace (e.g. an image generation) → a minimal **Request → Response** two-step timeline appears.

- [ ] **Step 3: Commit any formatting-only changes**

If `bun run lint` (which runs with `--fix`) modified any files, commit them:

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add -A frontend/src
git commit -m "style(traces): apply lint formatting

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

If nothing changed, skip this step.

---

### Task 8: Documentation

**Files:** docs updated via the `heym-documentation` skill (paths determined by the skill).

- [ ] **Step 1: Update the Traces documentation**

Invoke the `heym-documentation` skill and update the Traces section to describe:
- The new **Steps** timeline in the trace detail view (ordered system → user → assistant → tool → answer chain).
- Expand/collapse behavior: readable detail + the step's raw JSON shown automatically.
- That the full raw **Request/Response** JSON and the **Tool Calls** list remain available below the timeline.
- The minimal two-step Request → Response timeline for non-conversation traces.

- [ ] **Step 2: Commit the docs**

```bash
cd /Users/mbakgun/Projects/heym/heymrun
git add docs
git commit -m "docs: document Traces Steps timeline view

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Do not push.** This repo requires explicit user approval before any `git push`. Commit locally only.
- **No backend changes.** If you find yourself editing anything under `backend/`, stop — it is out of scope for this plan.
- **Language:** all UI strings are English (repo forbids Turkish in code/comments).
- **Import order** (enforced by lint): Vue imports → external libs → internal types (`import type`) → internal code. The snippets above already follow this; `bun run lint --fix` will reorder if needed.
