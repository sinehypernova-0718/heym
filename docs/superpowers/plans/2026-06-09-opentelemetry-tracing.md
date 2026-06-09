# OpenTelemetry Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **NO-COMMIT RULE (user directive):** Keep all changes local. Do NOT run `git commit` or `git push`. Every "Verify" checkpoint replaces what would normally be a commit.

**Goal:** Add OpenTelemetry tracing (workflow root span + per-node child spans + W3C trace-context propagation) to Heym, configured by env vars, surfaced read-only in a renamed "Settings" dialog with a gear icon.

**Architecture:** A new `app/observability/tracing.py` bootstraps the OTel SDK at FastAPI startup only when `HEYM_OTEL_ENABLED=true`. The workflow executor wraps `execute()` and `execute_node()` in spans, propagating OTel context into worker threads. FastAPI + httpx auto-instrumentation handle inbound webhook and outbound HTTP propagation. A read-only `GET /config/observability` endpoint backs the new Observability settings tab.

**Tech Stack:** Python 3.11, FastAPI, OpenTelemetry SDK + OTLP/HTTP exporter, Vue 3 + TypeScript, lucide-vue-next.

---

## File Structure

- Create: `backend/app/observability/__init__.py`
- Create: `backend/app/observability/tracing.py` (SDK bootstrap, tracer accessor, thread-context helpers)
- Create: `backend/app/api/observability.py` (read-only status endpoint)
- Create: `backend/tests/test_observability_tracing.py`
- Create: `frontend/src/docs/content/reference/opentelemetry.md`
- Modify: `backend/pyproject.toml` (deps)
- Modify: `backend/app/config.py` (`HEYM_OTEL_*` settings)
- Modify: `backend/app/main.py` (call `setup_tracing` / `shutdown_tracing` in lifespan; register router)
- Modify: `backend/app/services/workflow_executor.py` (spans in `execute`, `execute_node`, sub-workflow; thread-context capture)
- Modify: `frontend/src/components/Layout/AppHeader.vue` (gear icon, tooltip, initialTab type)
- Modify: `frontend/src/components/Layout/UserSettingsDialog.vue` (title, Observability tab, types)
- Modify: `frontend/src/services/api.ts` (`getObservabilityStatus`)
- Modify: `frontend/src/docs/manifest.ts` (reference entry)
- Modify: `frontend/src/docs/content/reference/user-settings.md` (Settings rename + Observability)
- Modify: `AGENTS.md`, `README` (if env table exists), `.env.example` (HEYM_OTEL_*)

---

## Task 1: Dependencies and configuration

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add OTel deps to `pyproject.toml`** under `[project]` `dependencies`:

```
"opentelemetry-sdk>=1.27.0",
"opentelemetry-exporter-otlp-proto-http>=1.27.0",
"opentelemetry-instrumentation-fastapi>=0.48b0",
"opentelemetry-instrumentation-httpx>=0.48b0",
```

- [ ] **Step 2: Install**

Run: `cd backend && uv sync`
Expected: lock updates, packages resolved.

- [ ] **Step 3: Add settings fields** to `Settings` in `app/config.py` (after `app_version`):

```python
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""
    otel_service_name: str = "heym"
    otel_traces_sampler_ratio: float = 1.0
    otel_capture_node_io: bool = False
```

pydantic-settings maps `HEYM_OTEL_ENABLED` only if an env prefix is set; this repo reads
bare names, so the env var names are `OTEL_ENABLED` style by default. Confirm the existing
`Config`/`model_config` env handling: if there is no prefix, document the actual accepted
names in the docs task. (Inspect `class Config` at bottom of `config.py` before finalizing
the documented names.)

- [ ] **Step 4: Verify** `python -c "from app.config import settings; print(settings.otel_enabled)"` prints `False`. Do NOT commit.

---

## Task 2: Tracing bootstrap module

**Files:**
- Create: `backend/app/observability/__init__.py` (empty)
- Create: `backend/app/observability/tracing.py`
- Test: `backend/tests/test_observability_tracing.py`

- [ ] **Step 1: Write failing test** in `tests/test_observability_tracing.py`:

```python
import unittest
from opentelemetry import trace

from app.observability import tracing


class TracingNoopTest(unittest.TestCase):
    def test_get_tracer_is_safe_when_disabled(self) -> None:
        tracer = tracing.get_tracer()
        with tracer.start_as_current_span("x") as span:
            span.set_attribute("heym.test", 1)
        # No provider configured -> no error, no export.
        self.assertIsNotNone(tracer)
```

- [ ] **Step 2: Run, expect fail** (`ModuleNotFoundError: app.observability`).

Run: `cd backend && uv run pytest tests/test_observability_tracing.py -q`

- [ ] **Step 3: Implement `tracing.py`:**

```python
"""OpenTelemetry tracing bootstrap. No-op unless HEYM_OTEL_ENABLED=true."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Tracer

from app.config import settings

logger = logging.getLogger(__name__)
_provider: Any = None
T = TypeVar("T")


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def setup_tracing(app: Any) -> None:
    """Configure the global tracer provider. Safe to call once at startup."""
    global _provider
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        resource = Resource.create(
            {
                "service.name": settings.otel_service_name or "heym",
                "service.version": settings.app_version or "dev",
            }
        )
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.otel_traces_sampler_ratio)),
        )
        exporter = OTLPSpanExporter(
            endpoint=(settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces")
            if settings.otel_exporter_otlp_endpoint
            else None,
            headers=_parse_headers(settings.otel_exporter_otlp_headers),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        logger.info("OpenTelemetry tracing enabled (endpoint=%s)",
                    settings.otel_exporter_otlp_endpoint)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize OpenTelemetry; tracing disabled")
        _provider = None


def shutdown_tracing() -> None:
    global _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:  # noqa: BLE001
            logger.exception("Error shutting down tracing provider")
        _provider = None


def get_tracer() -> Tracer:
    return trace.get_tracer("heym.workflow")


def capture_context() -> object:
    """Snapshot the active OTel context for re-attachment in a worker thread."""
    return otel_context.get_current()


def run_with_context(ctx: object, fn: Callable[[], T]) -> T:
    """Run fn with the given OTel context attached (for ThreadPoolExecutor workers)."""
    token = otel_context.attach(ctx)  # type: ignore[arg-type]
    try:
        return fn()
    finally:
        otel_context.detach(token)
```

- [ ] **Step 4: Run, expect pass.**

Run: `cd backend && uv run pytest tests/test_observability_tracing.py -q`
Expected: PASS.

- [ ] **Step 5: Verify locally. Do NOT commit.**

---

## Task 3: Wire bootstrap into FastAPI lifespan

**Files:**
- Modify: `backend/app/main.py:103-190` (lifespan + app creation)

- [ ] **Step 1:** In `app/main.py`, inside `lifespan`, after the FastAPI `app` is available
  for instrumentation: call `setup_tracing(app)` during startup and `shutdown_tracing()`
  during shutdown. Because `instrument_app` needs the `app` object, call `setup_tracing`
  right after `app = FastAPI(...)` is constructed (module level) OR pass `app` into
  lifespan. Simplest: add a module-level call `setup_tracing(app)` immediately after the
  `app = FastAPI(...)` definition (around line 186-190), and register `shutdown_tracing`
  via the lifespan's shutdown half.

```python
from app.observability.tracing import setup_tracing, shutdown_tracing
# ... after app = FastAPI(...) is defined:
setup_tracing(app)
```

In the lifespan shutdown section (after `yield`):

```python
    shutdown_tracing()
```

- [ ] **Step 2: Verify** the app imports cleanly:

Run: `cd backend && uv run python -c "import app.main"`
Expected: no error (tracing stays disabled by default).

- [ ] **Step 3: Verify locally. Do NOT commit.**

---

## Task 4: Workflow root span and node spans

**Files:**
- Modify: `backend/app/services/workflow_executor.py` (`execute` ~line 9692, `execute_node` ~line 6300)
- Test: `backend/tests/test_observability_tracing.py`

- [ ] **Step 1: Add a span test** using an in-memory exporter. Append to the test file:

```python
class WorkflowSpanTest(unittest.TestCase):
    def setUp(self) -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        self.exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        # Override the global provider for the duration of the test.
        trace._TRACER_PROVIDER = None  # reset so set works
        trace.set_tracer_provider(provider)

    def test_workflow_and_node_spans_emitted(self) -> None:
        # Build a minimal two-node workflow and execute it, then assert spans.
        # See helpers in tests/test_workflow_executor*.py for fixture patterns.
        ...
```

Note for implementer: reuse the smallest existing executor fixture from
`tests/` that builds nodes/edges and calls `execute_workflow(...)`. Assert that span names
`heym.workflow.execute` and `heym.node.execute` appear and carry `heym.workflow.id` /
`heym.node.type` attributes. If no light fixture exists, assert at the `execute_node`
level by instantiating `WorkflowExecutor` with a trivial Input -> Set graph.

- [ ] **Step 2: Run, expect fail** (no spans yet).

- [ ] **Step 3: Wrap `WorkflowExecutor.execute`.** At the top of `execute(self, workflow_id, initial_inputs)` (~9692), open a span around the body:

```python
from app.observability.tracing import get_tracer
from opentelemetry.trace import StatusCode

# inside execute(), wrapping the existing body:
tracer = get_tracer()
with tracer.start_as_current_span("heym.workflow.execute") as _wf_span:
    _wf_span.set_attribute("heym.workflow.id", str(workflow_id))
    _wf_span.set_attribute("heym.workflow.name", self.workflow_name or "")
    _wf_span.set_attribute("heym.execution.id", str(self.execution_id))
    _wf_span.set_attribute("heym.trigger.type", self.trigger_type or "manual")
    _wf_span.set_attribute("heym.node.count", len(self.nodes))
    try:
        # ... existing execute body ...
        return result
    except Exception as exc:
        _wf_span.record_exception(exc)
        _wf_span.set_status(StatusCode.ERROR)
        raise
```

Implementer: confirm the real attribute sources (`self.workflow_name`, `self.execution_id`,
`self.trigger_type`) by reading the `__init__` (line 1544). If a field is named
differently, use the actual field. Keep the import at module top, not inside the function.

- [ ] **Step 4: Wrap `execute_node`.** At the top of `execute_node(...)` (~6300):

```python
tracer = get_tracer()
node = self.get_node(node_id)  # use existing lookup
with tracer.start_as_current_span("heym.node.execute") as _node_span:
    _node_span.set_attribute("heym.node.id", str(node_id))
    _node_span.set_attribute("heym.node.label", self.get_node_label(node_id))
    _node_span.set_attribute("heym.node.type", node.get("type", "") if node else "")
    _node_span.set_attribute("heym.execution.id", str(self.execution_id))
    try:
        # ... existing execute_node body ...
        return node_result
    except Exception as exc:
        _node_span.record_exception(exc)
        _node_span.set_status(StatusCode.ERROR)
        raise
```

`get_node_label` already exists (line 1786). Use the existing node lookup pattern present
in `execute_node` rather than inventing `get_node` if it does not exist.

- [ ] **Step 5: Run, expect pass.** Adjust attribute assertions to match real values.

- [ ] **Step 6: Verify locally. Do NOT commit.**

---

## Task 5: Thread-context propagation for parallel nodes

**Files:**
- Modify: `backend/app/services/workflow_executor.py` (`execute_node_parallel` ~2515, and the ThreadPoolExecutor submit site)

- [ ] **Step 1: Add test** asserting a node span run in the parallel path still nests under
  the workflow span (same trace id). Reuse the WorkflowSpanTest provider. Build a graph
  with two sibling nodes that execute in parallel and assert both node spans share the
  workflow span's `trace_id`.

- [ ] **Step 2: Run, expect fail** (node spans get a different/empty trace id in threads).

- [ ] **Step 3: Capture and re-attach context.** At the parallel submit site, capture the
  current context before submitting and wrap the worker call:

```python
from app.observability.tracing import capture_context, run_with_context

_otel_ctx = capture_context()
# when submitting node work to the pool:
future = pool.submit(lambda: run_with_context(_otel_ctx, lambda: execute_and_report(node_id)))
```

Implementer: locate the actual `submit(...)` call(s) in `execute_node_parallel` /
`drain_bg_futures` and wrap the callable. Keep the existing function signature; only the
thread entry is wrapped.

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Verify locally. Do NOT commit.**

---

## Task 6: Sub-workflow span nesting (in-process)

**Files:**
- Modify: `backend/app/services/workflow_executor.py` (~3282 sub-agent tool, ~6916 sub-workflow)

- [ ] **Step 1:** Sub-executors run in-process inside a node's span context, so the
  sub-workflow root span automatically parents to the current node span once Task 4 is in
  place. Add an assertion test: executing a workflow whose node calls a sub-workflow yields
  a sub `heym.workflow.execute` span whose parent is the calling `heym.node.execute` span.
- [ ] **Step 2: Run.** If the sub-executor runs on a thread, apply the same
  `capture_context`/`run_with_context` wrapper from Task 5 at the sub-execution submit site.
- [ ] **Step 3: Verify locally. Do NOT commit.**

---

## Task 7: Read-only status endpoint

**Files:**
- Create: `backend/app/api/observability.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_observability_tracing.py`

- [ ] **Step 1: Write failing test** for the endpoint shape and secret safety:

```python
class StatusEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_shape_and_no_secrets(self) -> None:
        from app.api.observability import get_observability_status
        status = await get_observability_status()
        self.assertIn("enabled", status.model_dump())
        dumped = status.model_dump()
        self.assertNotIn("headers", dumped)
        self.assertEqual(dumped["instrumented"], ["fastapi", "httpx"]
                         if dumped["enabled"] else [])
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement `app/api/observability.py`:**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import User

router = APIRouter(prefix="/config", tags=["observability"])


class ObservabilityStatus(BaseModel):
    enabled: bool
    endpoint: str
    service_name: str
    sampler_ratio: float
    capture_node_io: bool
    instrumented: list[str]
    spans: list[str]


@router.get("/observability", response_model=ObservabilityStatus)
async def get_observability_status(
    _user: User = Depends(get_current_user),
) -> ObservabilityStatus:
    enabled = settings.otel_enabled
    return ObservabilityStatus(
        enabled=enabled,
        endpoint=settings.otel_exporter_otlp_endpoint if enabled else "",
        service_name=settings.otel_service_name,
        sampler_ratio=settings.otel_traces_sampler_ratio,
        capture_node_io=settings.otel_capture_node_io,
        instrumented=["fastapi", "httpx"] if enabled else [],
        spans=["workflow", "node"] if enabled else [],
    )
```

For the unit test, call the function with the auth dependency bypassed (call the inner
logic, or mark `_user` default). Match the test to however other endpoint unit tests in
this repo invoke handlers directly.

- [ ] **Step 4: Register router** in `app/main.py` alongside other routers:

```python
from app.api import observability
app.include_router(observability.router, prefix="/api")
```

Confirm the actual prefix convention used by neighboring `include_router` calls and match it.

- [ ] **Step 5: Run, expect pass.**

- [ ] **Step 6: Verify locally. Do NOT commit.**

---

## Task 8: Frontend - gear icon and Settings dialog

**Files:**
- Modify: `frontend/src/components/Layout/AppHeader.vue`
- Modify: `frontend/src/components/Layout/UserSettingsDialog.vue`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1:** In `AppHeader.vue`, replace the `User` import with `Settings` in the
  `lucide-vue-next` import, swap `<User .../>` for `<Settings .../>` in the user badge,
  change the button `title` to `"Settings"`, and widen `settingsInitialTab` type to
  `"profile" | "security" | "voice" | "observability"`.

- [ ] **Step 2:** In `api.ts`, add:

```typescript
export interface ObservabilityStatus {
  enabled: boolean;
  endpoint: string;
  service_name: string;
  sampler_ratio: number;
  capture_node_io: boolean;
  instrumented: string[];
  spans: string[];
}

export const observabilityApi = {
  async getStatus(): Promise<ObservabilityStatus> {
    const { data } = await api.get<ObservabilityStatus>("/config/observability");
    return data;
  },
};
```

Match the existing axios client import/name used by neighboring API objects in this file.

- [ ] **Step 3:** In `UserSettingsDialog.vue`:
  - Change the `Dialog` `title` from `"User Settings"` to `"Settings"`.
  - Widen both `initialTab` prop and `activeTab` ref unions to include `"observability"`.
  - Add an "Observability" tab button after "Voice".
  - Add a read-only Observability panel: on open (when tab active), call
    `observabilityApi.getStatus()` and render enabled badge, endpoint, service name,
    sampler ratio, the traced spans, plus a muted hint block listing the `HEYM_OTEL_*`
    env vars. No save button (read-only).

- [ ] **Step 4: Verify** lint + typecheck:

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS.

- [ ] **Step 5: Verify locally. Do NOT commit.**

---

## Task 9: Documentation (heym-documentation skill)

**Files:**
- Create: `frontend/src/docs/content/reference/opentelemetry.md`
- Modify: `frontend/src/docs/manifest.ts` (add `{ slug: "opentelemetry", title: "OpenTelemetry Tracing" }` under reference)
- Modify: `frontend/src/docs/content/reference/user-settings.md` (Settings rename + Observability tab)
- Modify: `AGENTS.md` (and README/.env.example if present) with `HEYM_OTEL_*` table

- [ ] **Step 1:** Use the `heym-documentation` skill to author `opentelemetry.md`: what it
  is, the env vars, what spans/attributes are emitted, propagation behavior, and a sample
  collector config. Keep em-dash usage minimal.
- [ ] **Step 2:** Add the manifest entry and update `user-settings.md`.
- [ ] **Step 3:** Add the env-var table to `AGENTS.md` and create/extend `.env.example`.
- [ ] **Step 4: Verify** `cd frontend && bun run typecheck` still passes (manifest is TS).
- [ ] **Step 5: Verify locally. Do NOT commit.**

---

## Task 10: Full verification

- [ ] **Step 1:** Run backend checks:

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./run_tests.sh`
Expected: all pass.

- [ ] **Step 2:** Run full gate:

Run: `SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./check.sh`
Expected: ruff format clean, lint clean, typecheck clean, tests pass.

- [ ] **Step 3:** Leave the working tree dirty and uncommitted. Report status to the user.

---

## Self-Review Notes

- Spec coverage: bootstrap (T2/T3), workflow span (T4), node span (T4), thread propagation
  (T5), inbound/outbound propagation (T3 instrumentation + T5/T6), sub-workflow (T6), status
  endpoint (T5/T7), frontend (T8), docs (T9), tests (T2/T4/T5/T6/T7), verification (T10).
- Env-var naming: Task 1 Step 3 flags the pydantic prefix question; resolve by reading
  `config.py`'s `Config` class so documented names match reality before Task 9.
- No commits anywhere, per user directive.
