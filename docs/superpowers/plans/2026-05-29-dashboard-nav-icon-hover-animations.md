# Dashboard Nav Icon Hover Animations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic per-icon CSS hover animations to `DashboardNav.vue` tab bar; text labels unchanged.

**Architecture:** Pure CSS — add a `tab-icon` class to the lucide icon element, define keyframe animations in `<style scoped>`, then apply each animation via `[data-tab-id="X"]:hover .tab-icon` selectors. No JS, no new dependencies.

**Tech Stack:** Vue 3 `<style scoped>`, CSS keyframes, Tailwind (not used for animations — scoped CSS only)

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `frontend/src/components/Layout/DashboardNav.vue` | Modify | Add `tab-icon` class to icon element; add CSS keyframes + hover rules + `prefers-reduced-motion` guard |

---

### Task 1: Add `tab-icon` class to icon element

**Files:**
- Modify: `frontend/src/components/Layout/DashboardNav.vue` (template section, the `<component :is="tab.icon">` element)

- [ ] **Step 1: Open the file and locate the icon element**

In `frontend/src/components/Layout/DashboardNav.vue`, find this block (around line 211):

```vue
<component
  :is="tab.icon"
  class="w-4 h-4"
/>
```

- [ ] **Step 2: Add `tab-icon` class**

Replace with:

```vue
<component
  :is="tab.icon"
  class="tab-icon w-4 h-4"
/>
```

- [ ] **Step 3: Verify the change looks right**

The button already has `class="tab-item ..."` and `[data-tab-id]` set. The icon now carries `tab-icon` so CSS can target `.tab-item[data-tab-id="X"]:hover .tab-icon`.

---

### Task 2: Add CSS keyframe definitions

**Files:**
- Modify: `frontend/src/components/Layout/DashboardNav.vue` (`<style scoped>` section)

- [ ] **Step 1: Add keyframe blocks to `<style scoped>`**

Append the following inside the existing `<style scoped>` block (after the last rule):

```css
/* --- icon hover animation keyframes --- */
@keyframes icon-spin {
  0%   { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes icon-tick {
  0%, 100% { transform: rotate(0deg); }
  25%       { transform: rotate(-15deg); }
  75%       { transform: rotate(10deg); }
}

@keyframes icon-pop {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.25); }
}

@keyframes icon-bounce {
  0%, 100% { transform: translateY(0); }
  40%       { transform: translateY(-4px); }
  70%       { transform: translateY(-2px); }
}

@keyframes icon-pulse {
  0%, 100% { transform: scale(1); }
  40%       { transform: scale(1.2); }
  70%       { transform: scale(0.95); }
}

@keyframes icon-slide {
  0%, 100% { transform: translateX(0); }
  40%       { transform: translateX(3px); }
  70%       { transform: translateX(1px); }
}

@keyframes icon-rotate {
  0%, 100% { transform: rotate(0deg); }
  40%       { transform: rotate(20deg); }
  70%       { transform: rotate(10deg); }
}

@keyframes icon-blink {
  0%, 100% { opacity: 1; }
  40%       { opacity: 0.3; }
  70%       { opacity: 0.7; }
}

@keyframes icon-wiggle {
  0%, 100% { transform: rotate(0deg); }
  15%       { transform: rotate(-12deg); }
  35%       { transform: rotate(12deg); }
  55%       { transform: rotate(-6deg); }
  75%       { transform: rotate(6deg); }
}

@keyframes icon-grow {
  0%, 100% { transform: scaleY(1); }
  30%       { transform: scaleY(0.7); }
  60%       { transform: scaleY(1.1); }
}

@keyframes icon-shake {
  0%, 100% { transform: translateX(0); }
  20%       { transform: translateX(-3px); }
  40%       { transform: translateX(3px); }
  60%       { transform: translateX(-2px); }
  80%       { transform: translateX(2px); }
}
```

---

### Task 3: Add per-tab hover rules and prefers-reduced-motion guard

**Files:**
- Modify: `frontend/src/components/Layout/DashboardNav.vue` (`<style scoped>` section, after keyframes from Task 2)

- [ ] **Step 1: Add one rule per tab**

Append after the keyframes:

```css
/* --- per-tab hover animations --- */
.tab-item[data-tab-id="workflows"]:hover     .tab-icon { animation: icon-spin   0.45s ease-out; }
.tab-item[data-tab-id="schedules"]:hover     .tab-icon { animation: icon-tick   0.40s ease-out; }
.tab-item[data-tab-id="templates"]:hover     .tab-icon { animation: icon-pop    0.35s ease-out; }
.tab-item[data-tab-id="globalvariables"]:hover .tab-icon { animation: icon-bounce 0.40s ease-out; }
.tab-item[data-tab-id="chat"]:hover          .tab-icon { animation: icon-pulse  0.40s ease-out; }
.tab-item[data-tab-id="drive"]:hover         .tab-icon { animation: icon-spin   0.50s ease-out; }
.tab-item[data-tab-id="datatable"]:hover     .tab-icon { animation: icon-slide  0.35s ease-out; }
.tab-item[data-tab-id="credentials"]:hover   .tab-icon { animation: icon-rotate 0.40s ease-out; }
.tab-item[data-tab-id="vectorstores"]:hover  .tab-icon { animation: icon-pulse  0.40s ease-out; }
.tab-item[data-tab-id="mcp"]:hover           .tab-icon { animation: icon-blink  0.50s ease-out; }
.tab-item[data-tab-id="traces"]:hover        .tab-icon { animation: icon-wiggle 0.50s ease-out; }
.tab-item[data-tab-id="analytics"]:hover     .tab-icon { animation: icon-grow   0.40s ease-out; }
.tab-item[data-tab-id="evals"]:hover         .tab-icon { animation: icon-shake  0.45s ease-out; }
.tab-item[data-tab-id="teams"]:hover         .tab-icon { animation: icon-bounce 0.40s ease-out; }
.tab-item[data-tab-id="logs"]:hover          .tab-icon { animation: icon-blink  0.50s ease-out; }
```

- [ ] **Step 2: Add `prefers-reduced-motion` guard**

Append immediately after the rules above:

```css
@media (prefers-reduced-motion: reduce) {
  .tab-icon {
    animation: none !important;
  }
}
```

---

### Task 4: Visual verification

**Files:** (no changes — manual browser check)

- [ ] **Step 1: Start the dev server**

```bash
cd /Users/mbakgun/Projects/heym/heymrun/frontend && bun run dev
```

Open `http://localhost:4017` in a browser.

- [ ] **Step 2: Verify each animation fires once on hover**

Hover over each of the 15 tabs and confirm:
- The icon animates once, then stops (no looping).
- The label text is unchanged.
- The active tab (purple background) also animates on hover.
- Moving the mouse away and back triggers the animation again.

- [ ] **Step 3: Verify no console errors**

Open DevTools console — expect no errors related to CSS or Vue.

---

### Task 5: Typecheck and commit

**Files:** (no new TS types — CSS-only change)

- [ ] **Step 1: Run TypeScript check**

```bash
cd /Users/mbakgun/Projects/heym/heymrun/frontend && bun run typecheck
```

Expected: no errors (change is CSS-only, no TS touched).

- [ ] **Step 2: Run lint**

```bash
cd /Users/mbakgun/Projects/heym/heymrun/frontend && bun run lint
```

Expected: no ESLint errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout/DashboardNav.vue
git commit -m "$(cat <<'EOF'
feat: add semantic hover animations to dashboard nav icons

Each of the 15 tab icons plays a one-shot CSS animation on hover
that matches its semantic meaning (spin, wiggle, bounce, etc.).
Text labels are unchanged. prefers-reduced-motion respected.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
