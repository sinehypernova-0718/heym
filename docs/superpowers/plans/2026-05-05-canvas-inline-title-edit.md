# Canvas Inline Workflow Title & Description Edit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to click the workflow title and description in the EditorView canvas header to edit them inline (desktop only), with immediate persistence to the backend.

**Architecture:** A new `updateMetadata` action is added to the workflow Pinia store and makes an optimistic update + revert-on-failure API call. EditorView replaces the static `<h1>` and `<p>` elements with click-to-edit inputs controlled by two local boolean refs.

**Tech Stack:** Vue 3 (Composition API, `<script setup>`), TypeScript strict, Pinia, Tailwind CSS

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/stores/workflow.ts` | Add `updateMetadata()` action; expose in return |
| `frontend/src/views/EditorView.vue` | Add local edit refs + handlers; update header template section (lines 993–1009) |

---

## Task 1: Add `updateMetadata` action to workflow store

**Files:**
- Modify: `frontend/src/stores/workflow.ts` (after `saveWorkflow`, around line 552)

> No backend tests needed: this calls the existing `workflowApi.update` which is already covered by the backend. Frontend tests don't exist yet (per AGENTS.md).

- [ ] **Step 1: Add the action after `saveWorkflow`**

Insert this function immediately after the closing brace of `saveWorkflow()` (after line 552):

```typescript
async function updateMetadata(name: string, description: string | null): Promise<void> {
  if (!currentWorkflow.value) return;

  const previousName = currentWorkflow.value.name;
  const previousDescription = currentWorkflow.value.description;
  currentWorkflow.value = { ...currentWorkflow.value, name, description };

  try {
    const updated = await workflowApi.update(currentWorkflow.value.id, { name, description });
    currentWorkflow.value = updated;
  } catch {
    currentWorkflow.value = { ...currentWorkflow.value, name: previousName, description: previousDescription };
    showToast("Failed to update workflow", "error", 3000);
  }
}
```

- [ ] **Step 2: Expose `updateMetadata` in the store return**

Find the `return {` block at the bottom of the store (around line 2183). Add `updateMetadata` next to `saveWorkflow`:

```typescript
    saveWorkflow,
    updateMetadata,
```

- [ ] **Step 3: Run typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/workflow.ts
git commit -m "feat: add updateMetadata action to workflow store"
```

---

## Task 2: Add inline edit refs and handlers in EditorView

**Files:**
- Modify: `frontend/src/views/EditorView.vue`

- [ ] **Step 1: Add `nextTick` to the Vue import**

Find the current import on line 2:

```typescript
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
```

Replace with:

```typescript
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
```

- [ ] **Step 2: Add local refs and handlers after line 110 (after `isSaving` computed)**

After this block:

```typescript
const isSaving = computed(() => workflowStore.isSaving);
```

Add:

```typescript
const isTitleEditing = ref(false);
const isDescriptionEditing = ref(false);
const editingTitleValue = ref("");
const editingDescriptionValue = ref("");
const titleInputRef = ref<HTMLInputElement | null>(null);
const descriptionInputRef = ref<HTMLInputElement | null>(null);

function startTitleEdit(): void {
  editingTitleValue.value = workflowStore.currentWorkflow?.name ?? "";
  isDescriptionEditing.value = false;
  isTitleEditing.value = true;
  void nextTick(() => {
    titleInputRef.value?.select();
  });
}

function commitTitleEdit(): void {
  const trimmed = editingTitleValue.value.trim();
  if (trimmed && trimmed !== workflowStore.currentWorkflow?.name) {
    void workflowStore.updateMetadata(trimmed, workflowStore.currentWorkflow?.description ?? null);
  }
  isTitleEditing.value = false;
}

function cancelTitleEdit(): void {
  isTitleEditing.value = false;
}

function startDescriptionEdit(): void {
  if (workflowStore.hasUnsavedChanges) return;
  editingDescriptionValue.value = workflowStore.currentWorkflow?.description ?? "";
  isTitleEditing.value = false;
  isDescriptionEditing.value = true;
  void nextTick(() => {
    descriptionInputRef.value?.focus();
  });
}

function commitDescriptionEdit(): void {
  const trimmed = editingDescriptionValue.value.trim();
  const newValue = trimmed || null;
  if (newValue !== (workflowStore.currentWorkflow?.description ?? null)) {
    void workflowStore.updateMetadata(
      workflowStore.currentWorkflow?.name ?? "",
      newValue,
    );
  }
  isDescriptionEditing.value = false;
}

function cancelDescriptionEdit(): void {
  isDescriptionEditing.value = false;
}
```

- [ ] **Step 3: Run typecheck**

```bash
cd frontend && bun run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/EditorView.vue
git commit -m "feat: add inline title/description edit refs and handlers to EditorView"
```

---

## Task 3: Update the header template in EditorView

**Files:**
- Modify: `frontend/src/views/EditorView.vue` (lines 993–1009 in template)

- [ ] **Step 1: Replace the static title/description block**

Find this exact block in the template (lines 993–1009):

```html
        <div class="hidden sm:block min-w-0">
          <h1 class="font-semibold text-sm md:text-base truncate max-w-[120px] sm:max-w-[150px] md:max-w-[250px]">
            {{ workflowName }}
          </h1>
          <p
            v-if="workflowDescription && !hasUnsavedChanges"
            class="text-xs text-muted-foreground truncate max-w-[120px] sm:max-w-[150px] md:max-w-[250px]"
          >
            {{ workflowDescription }}
          </p>
          <p
            v-else-if="hasUnsavedChanges"
            class="text-xs text-amber-500"
          >
            Unsaved changes
          </p>
        </div>
```

Replace with:

```html
        <div class="hidden sm:block min-w-0">
          <input
            v-if="isTitleEditing"
            ref="titleInputRef"
            v-model="editingTitleValue"
            class="font-semibold text-sm md:text-base bg-transparent border-b border-primary outline-none w-full max-w-[120px] sm:max-w-[150px] md:max-w-[250px]"
            maxlength="100"
            @blur="commitTitleEdit"
            @keydown.enter.prevent="commitTitleEdit"
            @keydown.escape="cancelTitleEdit"
          >
          <h1
            v-else
            class="font-semibold text-sm md:text-base truncate max-w-[120px] sm:max-w-[150px] md:max-w-[250px] cursor-text hover:bg-muted/50 rounded px-0.5 -mx-0.5"
            @click="startTitleEdit"
          >
            {{ workflowName }}
          </h1>
          <input
            v-if="isDescriptionEditing"
            ref="descriptionInputRef"
            v-model="editingDescriptionValue"
            class="text-xs text-muted-foreground bg-transparent border-b border-primary outline-none w-full max-w-[120px] sm:max-w-[150px] md:max-w-[250px]"
            maxlength="300"
            placeholder="Add description..."
            @blur="commitDescriptionEdit"
            @keydown.enter.prevent="commitDescriptionEdit"
            @keydown.escape="cancelDescriptionEdit"
          >
          <p
            v-else-if="hasUnsavedChanges"
            class="text-xs text-amber-500"
          >
            Unsaved changes
          </p>
          <p
            v-else-if="workflowDescription"
            class="text-xs text-muted-foreground truncate max-w-[120px] sm:max-w-[150px] md:max-w-[250px] cursor-text hover:bg-muted/50 rounded px-0.5 -mx-0.5"
            @click="startDescriptionEdit"
          >
            {{ workflowDescription }}
          </p>
          <p
            v-else
            class="text-xs text-muted-foreground/40 truncate max-w-[120px] sm:max-w-[150px] md:max-w-[250px] cursor-text hover:bg-muted/50 rounded px-0.5 -mx-0.5"
            @click="startDescriptionEdit"
          >
            Add description...
          </p>
        </div>
```

- [ ] **Step 2: Run lint and typecheck**

```bash
cd frontend && bun run lint && bun run typecheck
```

Expected: no errors or warnings.

- [ ] **Step 3: Start dev server and manually verify**

```bash
cd frontend && bun run dev
```

Open `http://localhost:4017`, open a workflow in the editor, and verify:

1. On desktop (sm+): clicking the title replaces it with an input pre-filled with the current name and selected
2. Enter saves and the new name persists after page refresh
3. Escape cancels without saving
4. Blur (clicking away) saves if value changed and non-empty
5. Empty title on blur/Enter reverts to previous name without API call
6. Clicking description opens input; Enter/blur/Escape behave the same
7. "Add description..." placeholder shows when description is empty
8. "Unsaved changes" badge still appears correctly when nodes/edges are changed
9. On mobile (below sm): title/description area is hidden — no edit UI visible

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/EditorView.vue
git commit -m "feat: inline editable workflow title and description in canvas header"
```

---

## Task 4: Final check

- [ ] **Step 1: Run full check**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym && ./check.sh
```

Expected: lint passes, typecheck passes, backend tests pass.

- [ ] **Step 2: Commit formatting fixes if any**

If `./check.sh` produces a formatting-only diff:

```bash
git add -A && git commit -m "chore: apply ruff formatting"
```
