# OpenTelemetry Tracing for Heym Workflows

Date: 2026-06-09
Status: Approved (implementation kept local, not committed yet)

## Goal

Add OpenTelemetry (OTel) tracing to Heym so that workflow and node executions can be
observed in any OTLP-compatible backend (Jaeger, Grafana Tempo, Honeycomb, Datadog,
New Relic, etc.). This mirrors n8n's OpenTelemetry integration: a root span per workflow
execution, child spans per node, and W3C trace-context propagation across webhooks,
outbound HTTP calls, and sub-workflows.

Two UI changes ship alongside the backend work:

1. The dialog that opens from the header user button is renamed from "User Settings" to
   "Settings", gains an "Observability" item (tab), and the header `User` icon becomes a
   gear (`Settings`) icon.
2. Docs and configuration (env vars, `.env.example`, in-app reference page) are updated.

## Non-Goals

- No admin/role system. Heym has no admin role, so OTel is an instance-level concern.
- No DB-backed OTel config in v1. Configuration is via environment variables only. The
  Observability tab is read-only status, not an editor. Secrets (OTLP auth headers) never
  enter the database and are never returned by the status endpoint.
- No metrics or logs pipeline in v1. Traces only.

## Configuration (env vars)

All disabled by default, so there is zero runtime overhead unless explicitly enabled.

| Env var | Default | Purpose |
| --- | --- | --- |
| `HEYM_OTEL_ENABLED` | `false` | Master switch. When false, tracing setup is a no-op. |
| `HEYM_OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP/HTTP base endpoint, e.g. `http://collector:4318`. |
| `HEYM_OTEL_EXPORTER_OTLP_HEADERS` | `""` | Comma-separated `key=value` headers for exporter auth (e.g. vendor API key). |
| `HEYM_OTEL_SERVICE_NAME` | `heym` | `service.name` resource attribute. |
| `HEYM_OTEL_TRACES_SAMPLER_RATIO` | `1.0` | Ratio for `ParentBased(TraceIdRatioBased)` sampler. |
| `HEYM_OTEL_CAPTURE_NODE_IO` | `false` | When true, attach truncated node input/output JSON to node spans. Off by default for privacy. |

These are added to `app/config.py` (`Settings`), `.env.example`, and AGENTS.md/README.

## Architecture

### Component 1: Tracing bootstrap (`backend/app/observability/tracing.py`, new)

A single module owns SDK setup and helpers. Public surface:

- `setup_tracing(app: FastAPI) -> None`: called once from `lifespan` startup in
  `app/main.py`. If `settings.otel_enabled` is false, returns immediately (global tracer
  stays the SDK no-op, every span call is cheap). If true:
  - Build `Resource` with `service.name`, `service.version` (from `settings.app_version`).
  - Create `TracerProvider(resource=..., sampler=ParentBased(TraceIdRatioBased(ratio)))`.
  - Add `BatchSpanProcessor(OTLPSpanExporter(endpoint, headers))` (OTLP/HTTP protobuf).
    Batch processing is async and non-blocking, so a slow or unreachable collector never
    blocks workflow execution.
  - `trace.set_tracer_provider(provider)`.
  - `FastAPIInstrumentor.instrument_app(app)` for inbound context extraction.
  - `HTTPXClientInstrumentor().instrument()` for outbound `traceparent` injection.
  - Store the provider so `shutdown_tracing()` can flush on lifespan shutdown.
  - The whole body is wrapped in try/except and logs on failure, so a misconfiguration
    degrades to "no tracing" instead of breaking startup.
- `shutdown_tracing() -> None`: flush + shutdown provider on app shutdown.
- `get_tracer() -> Tracer`: returns `trace.get_tracer("heym.workflow")`.
- `current_otel_context()` / `run_with_otel_context(ctx, fn)`: helpers to capture the
  active OTel context and re-attach it inside worker threads (see Component 3).

Dependencies added to `pyproject.toml`:
`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
`opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`.

### Component 2: Workflow and node spans (`backend/app/services/workflow_executor.py`)

- Root span `heym.workflow.execute` wraps `WorkflowExecutor.execute()` (around line 9692).
  Attributes:
  - `heym.workflow.id`, `heym.workflow.name`
  - `heym.execution.id`
  - `heym.trigger.type` (manual, webhook, cron, telegram, imap, websocket, rabbitmq, ...)
  - `heym.node.count`
  On exception: `span.record_exception(e)` + `span.set_status(StatusCode.ERROR)`.
- Node span `heym.node.execute` wraps `execute_node()` (around line 6300). Attributes:
  - `heym.node.id`, `heym.node.label`, `heym.node.type`
  - `heym.execution.id`
  - For LLM/agent nodes (reusing existing `llm_trace` data): `heym.llm.model`,
    `heym.llm.prompt_tokens`, `heym.llm.completion_tokens`, `heym.llm.total_tokens`,
    `heym.llm.cost_usd`.
  - If `otel_capture_node_io` is on: truncated `heym.node.input` / `heym.node.output`.
  On node error: record exception + ERROR status. The existing error-flow logic is
  unchanged; spans observe it, they do not alter control flow.
- All custom attributes use the `heym.*` prefix to avoid clashing with OTel semantic
  conventions.

### Component 3: Thread-context propagation (critical)

`WorkflowExecutor` runs nodes in a `ThreadPoolExecutor` (`execute_node_parallel`,
`drain_bg_futures`). OTel context is `contextvars`-based and does not cross threads
automatically. Without handling this, node spans would detach from the workflow span.

Fix: at the point where the executor submits node work to the pool, capture
`opentelemetry.context.get_current()` and, inside the worker, `context.attach(captured)`
(and `detach` in a finally). A small wrapper in `tracing.py` encapsulates this so the
executor call sites stay readable. This guarantees node spans nest under the workflow
span even when run in parallel worker threads.

### Component 4: Trace-context propagation across boundaries

- Inbound (webhooks/triggers): `FastAPIInstrumentor` extracts a `traceparent` header into
  the request's OTel context and creates a server span. The webhook trigger path captures
  that context and passes it into the executor thread, so the workflow root span becomes a
  child of the caller's trace. Background triggers (cron, queue consumers) have no inbound
  context, so they start a fresh trace.
- Outbound (HTTP node): the executor's shared `httpx.Client` (around line 444) is
  instrumented by `HTTPXClientInstrumentor`, which injects `traceparent` into outgoing
  requests automatically. Instrumentation runs at startup before the lazily-created client
  is first used.
- Sub-workflows / sub-agents (around lines 3282 and 6916): the sub-executor's root span
  parents to the current node span via in-process context, preserving hierarchy.

### Component 5: Read-only status endpoint (`backend/app/api/`)

`GET /config/observability` (auth required) returns a Pydantic model:

```json
{
  "enabled": true,
  "endpoint": "http://collector:4318",
  "service_name": "heym",
  "sampler_ratio": 1.0,
  "capture_node_io": false,
  "instrumented": ["fastapi", "httpx"],
  "spans": ["workflow", "node"]
}
```

OTLP header values are never included. This backs the Observability tab.

### Component 6: Frontend (Settings dialog + gear icon)

- `AppHeader.vue`: import `Settings` instead of `User` from `lucide-vue-next`; the header
  user button shows the gear icon (name text stays), tooltip becomes "Settings".
- `UserSettingsDialog.vue`: dialog title "User Settings" becomes "Settings"; the tab union
  `"profile" | "security" | "voice"` gains `"observability"`; a new "Observability" tab
  renders read-only status fetched from `GET /config/observability` (enabled badge,
  endpoint, service name, what is traced, sampler) plus a hint block listing the
  `HEYM_OTEL_*` env vars used to configure it. The `initialTab` prop union is widened
  accordingly, and `AppHeader.vue`'s `settingsInitialTab` type is updated.
- `frontend/src/services/api.ts`: add `getObservabilityStatus()`.

## Failure modes and safety

- Disabled by default: no SDK init, no spans exported, no measurable overhead.
- Exporter errors are swallowed by `BatchSpanProcessor`; they never propagate into
  workflow execution.
- Bootstrap failures degrade to "tracing off" and are logged, never fatal.
- No secrets stored in DB or returned by the API.

## Testing (`backend/tests/test_observability_tracing.py`)

Use the OTel SDK `InMemorySpanExporter` with a `SimpleSpanProcessor` fixture.

- Disabled: `setup_tracing` is a no-op; executing a small workflow runs without producing
  spans and without errors.
- Enabled: executing a small two-node workflow yields one `heym.workflow.execute` root
  span and child `heym.node.execute` spans with the expected `heym.*` attributes.
- Error path: a failing node marks its span status ERROR and records the exception.
- Propagation: an inbound `traceparent` results in a workflow span sharing the inbound
  trace id (context-based assertion).
- Status endpoint: returns the documented shape and never leaks header/secret values.

Frontend has no test harness (per repo convention); verify via lint + typecheck + manual.

## Documentation

- New `frontend/src/docs/content/reference/opentelemetry.md` plus a manifest entry
  `{ slug: "opentelemetry", title: "OpenTelemetry Tracing" }` under the Reference category.
- Update `reference/user-settings.md` for the Settings rename and the Observability tab.
- AGENTS.md / README: `HEYM_OTEL_*` env-var table and `.env.example` additions.
- Use the `heym-documentation` skill for the in-app docs.
- heymweb: a separate follow-up. A marketing/blog page about observability is written via
  the SEO skill pipeline, and in-app docs are synced with `bun run sync-docs`. The blog
  effort is tracked outside this implementation plan.

## Rollout

Ship disabled. Operators opt in by setting `HEYM_OTEL_ENABLED=true` and an OTLP endpoint.
No migration is required because there is no schema change.
