# Runbook — Self-Driving Animated Demo — Design

**Date:** 2026-06-09
**Status:** Approved design (pending written-spec review)

## Overview

The **Runbook** is a self-driving, animated, instructive demo that builds and runs a *real* Heym
workflow from existing credential-free nodes. A user triggers it from one of three entry points and
then simply watches: nodes slide in from the left one at a time, the workflow auto-runs, and the
console node logs an uppercase line. No arrows, no "click here" tooltips, no required user action.

It is **not** an LLM demo and **not** a faked/simulated tour. It uses three real node types that
already exist in Heym and runs through the real executor.

### The demo workflow

```
textInput ("Heym is an ai native automation platform")  →  wait (2000ms)  →  consoleLog ($input.text.upper())
```

- `textInput` — sample input value `"Heym is an ai native automation platform"`.
- `wait` — `duration: 2000` (the real 2s pause during execution doubles as the "watch it run" beat).
- `consoleLog` — `logMessage: "$input.text.upper()"` → logs `HEYM IS AN AI NATIVE AUTOMATION PLATFORM`
  via the consoleLog node's existing output path. The DSL supports `.upper()`
  (`frontend/src/docs/content/reference/expression-dsl.md`).

All three nodes are credential-free, so the run can never fail on missing setup.

## Goals

- One reusable orchestration ("runbook player") drives all entry points.
- Everything is real: real nodes added to the canvas, real connections, real `executeWorkflow()`.
- The build is **animated and step-by-step** (instructive), not loaded all at once.
- Self-driving — the user takes no action after triggering.
- Respects `prefers-reduced-motion`.

## Non-Goals

- No LLM/agent nodes, no credentials, no API keys.
- No faked/simulated execution overlay.
- No guided "click here / next" tooltips or arrow callouts.
- No new backend node types (uses existing `textInput`, `wait`, `consoleLog`).

## Key Constraints (discovered in code)

- The editor route is always `/workflows/:id` (`frontend/src/router/index.ts`). There is **no purely
  in-memory canvas** — the editor always operates on a persisted workflow.
- `executeWorkflow(body)` requires `currentWorkflow.value` and runs against `wf.id`, auto-saving via
  `saveWorkflow()` first; `saveWorkflow` only **updates** an existing id (it does not create)
  (`frontend/src/stores/workflow.ts:540`, `:1078`).
- Therefore a "run" always needs a real, persisted workflow. The "temp/scratch canvas" is realized as
  a **freshly created real workflow**, not an in-memory throwaway.
- Run body is built by `workflowStore.buildExecutionRequestBody()` from `runInputValues` /
  `runInputJson` (`frontend/src/stores/workflow.ts:159`). The player sets the input value, then runs
  `executeWorkflow(buildExecutionRequestBody())`.
- Node creation defaults live in `getDefaultNodeData()` (`frontend/src/components/Canvas/WorkflowCanvas.vue:819`):
  `textInput: { label: "start", value: "", inputFields: [{ key: "text" }] }`,
  `wait: { label: "wait", duration: 1000 }`,
  `consoleLog: { label: "consoleLog", logMessage: "$input" }`.
- Nodes are added via `workflowStore.addNode(node)` (`frontend/src/stores/workflow.ts:590`).

## Architecture

### Approach (chosen): shared "runbook player" composable

A single `useRunbookPlayer()` orchestrates the entire flow; all three entry points call it. It adds
almost no new infrastructure — it sequences store functions that already exist.

Rejected alternatives:
- **Prebuilt template + auto-run** — nodes appear all at once; loses the animated/instructive build.
- **Pure visual overlay (fake)** — contradicts the "real nodes + real run" requirement.

### New files

```
frontend/src/features/runbook/
├── runbookScript.ts          # The 3-node script: types, sample text, uppercase log expr, layout offsets, timings
├── useRunbookPlayer.ts       # Orchestration composable + shared play state
└── components/
    └── CanvasEmptyState.vue  # Empty-canvas starter UI (Run the runbook / Browse templates)
```

Module-level singleton state inside `useRunbookPlayer` holds `isPlaying` / current-step so
re-triggers are ignored while a run is active (shared across all callers without a new Pinia store).

### `runbookScript.ts`

Declarative description of the demo so the choreography and the backend test share one source of truth:

```ts
export const RUNBOOK_INPUT_TEXT = "Heym is an ai native automation platform";
export const RUNBOOK_LOG_EXPRESSION = "$input.text.upper()";

export interface RunbookStep {
  type: NodeType;            // "textInput" | "wait" | "consoleLog"
  data: Partial<NodeData>;   // overrides merged over getDefaultNodeData(type)
  enterDelayMs: number;      // beat before this node slides in
}
// Steps: textInput(value=RUNBOOK_INPUT_TEXT) → wait(duration=2000) → consoleLog(logMessage=RUNBOOK_LOG_EXPRESSION)
```

### `useRunbookPlayer.ts`

```ts
type RunbookMode = "newWorkflow" | "inPlace";

function playRunbook(mode: RunbookMode): Promise<void>
```

Flow:
1. Guard: if already playing, ignore.
2. **`newWorkflow`** — `workflowApi.create({ name: "Runbook — Heym demo", ... })`, then
   `router.push({ name: "editor", params: { id } })`, and await editor/canvas ready (workflow loaded,
   canvas mounted).
   **`inPlace`** — use the current (empty) workflow; no navigation.
3. For each step: wait `enterDelayMs`, build node data = `{ ...getDefaultNodeData(type), ...data }`,
   position it left→right using existing layout spacing, mark it "just added" (entrance animation),
   `addNode(...)`, and add an edge from the previous node.
4. Fit the viewport to the built graph.
5. Set the input value (`runInputValues` / `runInputJson`) to `RUNBOOK_INPUT_TEXT`, then
   `executeWorkflow(buildExecutionRequestBody())`.
6. Clear `isPlaying` when the run settles.

The `getDefaultNodeData` map is currently local to `WorkflowCanvas.vue`; to avoid drift it will be
extracted to a shared module (e.g. `frontend/src/lib/nodeDefaults.ts`) and imported by both the canvas
and the runbook player.

## Entry Points

### 1. Ctrl+K command palette
- File: `frontend/src/components/Dialogs/WorkflowCommandPalette.vue`.
- Add a new `PaletteItemType` `"runbook"` and a new item in the existing **"Support"** group
  (next to "Contact Support"). Label: **"Run the Runbook"**; subtitle e.g. *"Watch Heym build & run a
  workflow"*. Searchable via `runbook / demo / support / tour / guide`.
- On select: emit a new `runbook` event to the host (DashboardView / EditorView), which calls
  `playRunbook("newWorkflow")` and closes the palette.

### 2. Guidelines (showcase) panel footer
- Files: `frontend/src/features/showcase/components/ShowcasePanel.vue` (desktop) and
  `ShowcaseMobileSheet.vue` (mobile) — add a button **below all guideline actions** in the footer
  action list. Mirrors the existing footer button styling.
- Wiring: `ShowcasePanel`/`ShowcaseMobileSheet` emit `runbook` → `ContextualShowcase.vue` handler →
  `playRunbook("newWorkflow")` (closing the showcase first).

### 3. Empty canvas
- New component `CanvasEmptyState.vue`, rendered as a centered overlay in
  `frontend/src/components/Canvas/WorkflowCanvas.vue` when `workflowStore.nodes.length === 0`.
- Shows two starter actions:
  - **"Run the runbook"** → `playRunbook("inPlace")` (plays on the current empty workflow; no navigation).
  - **"Browse templates"** → opens the existing template path (command palette templates / templates page).
- Hidden as soon as the first node exists (so it disappears the instant the runbook adds `textInput`).

## Animation & Accessibility

- Each freshly added node gets a transient "just added" flag → a CSS slide-in-from-left entrance
  applied in `BaseNode.vue` (translateX + fade), cleared after the transition.
- Beats between steps come from `enterDelayMs` so the build reads as deliberate, not instant.
- `prefers-reduced-motion: reduce` → no transforms/delays; nodes are placed instantly and the workflow
  still builds and runs. (Matches existing reduced-motion handling in showcase/command-palette styles.)
- Viewport auto-fits so the user never has to pan/zoom.

## Canvas Lifecycle

- **From menus (`newWorkflow`):** creates a real workflow named **"Runbook — Heym demo"**, navigates
  to it, builds + runs. **Kept** afterward (per decision) — a normal saved workflow the user can
  explore, re-run, or delete. Each menu trigger creates a fresh one.
- **From empty canvas (`inPlace`):** uses the current workflow (already has an id), builds + runs in place.

## Edge Cases

- Re-trigger while playing → ignored (`isPlaying` guard).
- Navigation race in `newWorkflow` → await canvas-ready before adding nodes.
- User navigates away mid-play → player aborts cleanly (cancel pending timers; existing run abort path).
- `inPlace` on a non-empty canvas → not exposed (the empty-state UI only shows when there are 0 nodes),
  so the player assumes an empty canvas in that mode.

## Testing

- **Frontend:** no FE test harness in this repo (per project convention). Verify via
  `bun run lint` + `bun run typecheck` + manual run of all three entry points.
- **Backend (required):** add a pytest under `backend/tests/` that executes the exact
  `textInput → wait → consoleLog` graph end-to-end with input `"Heym is an ai native automation
  platform"` and asserts the consoleLog step resolves `$input.text.upper()` to
  `"HEYM IS AN AI NATIVE AUTOMATION PLATFORM"`. This locks the demo's contract so future node/DSL
  changes can't silently break the runbook.
- Run `./check.sh` before pushing.

## Documentation

Medium feature with new UI → update docs via the `heym-documentation` skill (e.g. a short
"Runbook" reference page and a mention in keyboard-shortcuts / quick-start).

## Open Questions

None — both prior open decisions resolved:
- Demo workflow is **kept** (clearly named "Runbook — Heym demo").
- consoleLog message uses the **expression** `$input.text.upper()`.
