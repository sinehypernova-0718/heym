# Canvas Inline Workflow Title & Description Edit

**Date:** 2026-05-05
**Status:** Approved
**Scope:** Browser-only (desktop), EditorView canvas header

## Overview

Add click-to-edit inline editing for the workflow title and description in the EditorView canvas header. Only available on desktop (`sm:` breakpoint and above); mobile is unaffected. Changes are persisted immediately to the backend, independent of node/edge unsaved changes.

## Data Flow & Store

A new `updateMetadata(name: string, description: string | null)` action is added to the workflow Pinia store (`frontend/src/stores/workflow.ts`).

- Calls existing `workflowApi.update(id, { name, description })`
- On success: updates `currentWorkflow.name` and `currentWorkflow.description`
- On failure: reverts `currentWorkflow` to pre-call values and shows an error toast
- Does NOT touch `hasUnsavedChanges` — metadata saves are independent of node/edge changes

## UI Behavior

The `hidden sm:block` div in the EditorView header contains the title and description. Changes:

**Normal state:**
- Title renders as `<h1>` and description as `<p>` (unchanged visually)
- Hover shows `cursor-text` and a subtle background tint to signal editability

**Edit state — title:**
- Clicking the title replaces `<h1>` with an `<input>`, pre-filled with the current name and fully selected
- Enter or blur: calls `updateMetadata()` if value changed and is non-empty; reverts to previous value otherwise
- Escape: cancels edit, restores previous value without API call

**Edit state — description:**
- Clicking the description (or the placeholder if empty) replaces `<p>` with an `<input>`
- Same Enter/blur/Escape behavior as title
- When no description exists, a placeholder text "Add description..." is shown so users have a click target

**Constraints:**
- Only one field (title or description) can be in edit mode at a time
- The "Unsaved changes" badge replaces the description display when `hasUnsavedChanges` is true — this behavior is preserved unchanged

## Error Handling & Edge Cases

| Case | Behavior |
|------|----------|
| Title left empty | Do not call API; revert to previous value |
| No change on blur | Do not call API |
| API error | Revert `currentWorkflow` to pre-call values; show error toast |
| Concurrent node save in progress | Allowed — metadata and node saves are independent |
| Max length | `maxlength="100"` on title, `maxlength="300"` on description |

## Files to Change

| File | Change |
|------|--------|
| `frontend/src/stores/workflow.ts` | Add `updateMetadata()` action |
| `frontend/src/views/EditorView.vue` | Replace static title/description with inline-edit UI; add `isTitleEditing`, `isDescriptionEditing` local refs and handler functions |

## Non-Goals

- Mobile edit (no change on `xs` / below `sm` breakpoint)
- Separate component extraction (keep changes in EditorView)
- Rename functionality in DashboardView is unchanged
