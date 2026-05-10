<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useVueFlow } from "@vue-flow/core";
import DOMPurify from "dompurify";
import { marked } from "marked";

import type { NodeData, StickyNoteColor } from "@/types/workflow";

import { cn } from "@/lib/utils";
import { useWorkflowStore } from "@/stores/workflow";

interface Props {
  id: string;
  data: NodeData;
  selected?: boolean;
  resizable?: boolean;
}

const props = defineProps<Props>();
const workflowStore = useWorkflowStore();

const { viewport } = useVueFlow();

interface StickyColorTheme {
  container: string;
  header: string;
  input: string;
  resize: string;
  swatch: string;
}

const STICKY_COLOR_THEMES: Record<StickyNoteColor, StickyColorTheme> = {
  yellow: {
    container: "bg-yellow-100/90 dark:bg-yellow-950/50 border-yellow-300 dark:border-yellow-700 text-yellow-950 dark:text-yellow-50",
    header: "text-yellow-900/85 dark:text-yellow-100/85",
    input: "border-yellow-300/70 dark:border-yellow-700/70 focus:ring-yellow-400",
    resize: "text-yellow-800 dark:text-yellow-200",
    swatch: "bg-yellow-300 dark:bg-yellow-500",
  },
  sky: {
    container: "bg-sky-100/90 dark:bg-sky-950/55 border-sky-300 dark:border-sky-700 text-sky-950 dark:text-sky-50",
    header: "text-sky-900/85 dark:text-sky-100/85",
    input: "border-sky-300/70 dark:border-sky-700/70 focus:ring-sky-400",
    resize: "text-sky-800 dark:text-sky-200",
    swatch: "bg-sky-300 dark:bg-sky-500",
  },
  emerald: {
    container: "bg-emerald-100/90 dark:bg-emerald-950/55 border-emerald-300 dark:border-emerald-700 text-emerald-950 dark:text-emerald-50",
    header: "text-emerald-900/85 dark:text-emerald-100/85",
    input: "border-emerald-300/70 dark:border-emerald-700/70 focus:ring-emerald-400",
    resize: "text-emerald-800 dark:text-emerald-200",
    swatch: "bg-emerald-300 dark:bg-emerald-500",
  },
  rose: {
    container: "bg-rose-100/90 dark:bg-rose-950/55 border-rose-300 dark:border-rose-700 text-rose-950 dark:text-rose-50",
    header: "text-rose-900/85 dark:text-rose-100/85",
    input: "border-rose-300/70 dark:border-rose-700/70 focus:ring-rose-400",
    resize: "text-rose-800 dark:text-rose-200",
    swatch: "bg-rose-300 dark:bg-rose-500",
  },
  violet: {
    container: "bg-violet-100/90 dark:bg-violet-950/55 border-violet-300 dark:border-violet-700 text-violet-950 dark:text-violet-50",
    header: "text-violet-900/85 dark:text-violet-100/85",
    input: "border-violet-300/70 dark:border-violet-700/70 focus:ring-violet-400",
    resize: "text-violet-800 dark:text-violet-200",
    swatch: "bg-violet-300 dark:bg-violet-500",
  },
  zinc: {
    container: "bg-zinc-100/90 dark:bg-zinc-900/80 border-zinc-300 dark:border-zinc-700 text-zinc-950 dark:text-zinc-50",
    header: "text-zinc-800/85 dark:text-zinc-100/85",
    input: "border-zinc-300/70 dark:border-zinc-700/70 focus:ring-zinc-400",
    resize: "text-zinc-800 dark:text-zinc-200",
    swatch: "bg-zinc-300 dark:bg-zinc-500",
  },
};

const STICKY_COLORS: StickyNoteColor[] = ["yellow", "sky", "emerald", "rose", "violet", "zinc"];
const DEFAULT_TITLE = "Sticky Note";

const isEditingNote = ref(false);
const isEditingTitle = ref(false);
const isPaletteHovered = ref(false);
const isPaletteVisible = ref(false);
const localNote = ref(props.data.note || "");
const localTitle = ref(props.data.stickyTitle || DEFAULT_TITLE);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const titleInputRef = ref<HTMLInputElement | null>(null);
const containerRef = ref<HTMLDivElement | null>(null);

const MIN_WIDTH = 200;
const MIN_HEIGHT = 80;

const localWidth = ref<number | null>(props.data.stickyWidth ?? null);
const localHeight = ref<number | null>(props.data.stickyHeight ?? null);

let isResizingActive = false;
let resizeStartX = 0;
let resizeStartY = 0;
let resizeStartWidth = 0;
let resizeStartHeight = 0;

watch(
  () => props.data.note,
  (value) => {
    if (!isEditingNote.value) {
      localNote.value = value || "";
    }
  }
);

watch(
  () => props.data.stickyTitle,
  (value) => {
    if (!isEditingTitle.value) {
      localTitle.value = value || DEFAULT_TITLE;
    }
  }
);

watch(
  () => [props.data.stickyWidth, props.data.stickyHeight] as const,
  ([w, h]) => {
    if (!isResizingActive) {
      localWidth.value = w ?? null;
      localHeight.value = h ?? null;
    }
  }
);

const containerStyle = computed(() => {
  const style: Record<string, string> = {};
  if (localWidth.value !== null) {
    style.width = `${localWidth.value}px`;
  }
  if (localHeight.value !== null) {
    style.height = `${localHeight.value}px`;
  }
  return style;
});

const hasExplicitSize = computed(() => localWidth.value !== null || localHeight.value !== null);
const canEdit = computed(() => props.resizable === true);
const currentColor = computed<StickyNoteColor>(() => props.data.stickyColor ?? "yellow");
const colorTheme = computed<StickyColorTheme>(() => STICKY_COLOR_THEMES[currentColor.value]);
const displayTitle = computed(() => props.data.stickyTitle || DEFAULT_TITLE);
const shouldShowPalette = computed(() => isPaletteVisible.value || isPaletteHovered.value);

function renderMarkdown(raw: string): string {
  const html = marked(raw, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["target", "rel"],
  });
}

const renderedNote = computed(() => {
  const value = (props.data.note || "").trim();
  const content = value.length > 0 ? value : "Double click to edit";
  return renderMarkdown(content);
});

function startNoteEditing(): void {
  if (!canEdit.value) return;
  isEditingNote.value = true;
  localNote.value = props.data.note || "";
  nextTick(() => textareaRef.value?.focus());
}

function stopNoteEditing(): void {
  if (!isEditingNote.value) return;
  isEditingNote.value = false;
  workflowStore.updateNode(props.id, { note: localNote.value });
}

function startTitleEditing(): void {
  if (!canEdit.value) return;
  isEditingTitle.value = true;
  localTitle.value = props.data.stickyTitle || DEFAULT_TITLE;
  nextTick(() => titleInputRef.value?.focus());
}

function stopTitleEditing(): void {
  if (!isEditingTitle.value) return;
  const nextTitle = localTitle.value.trim() || DEFAULT_TITLE;
  localTitle.value = nextTitle;
  isEditingTitle.value = false;
  workflowStore.updateNode(props.id, { stickyTitle: nextTitle });
}

function setColor(color: StickyNoteColor): void {
  if (!canEdit.value || color === currentColor.value) return;
  workflowStore.updateNode(props.id, { stickyColor: color });
}

function updatePaletteVisibility(event: MouseEvent): void {
  if (!canEdit.value || isPaletteHovered.value) return;
  const el = containerRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const pointerY = event.clientY - rect.top;
  const lowerTriggerY = rect.height * 0.8;
  const paletteTravelY = rect.height + 50;
  isPaletteVisible.value = pointerY >= lowerTriggerY && pointerY <= paletteTravelY;
}

function hidePaletteIfIdle(): void {
  if (isPaletteHovered.value) return;
  isPaletteVisible.value = false;
}

function startResize(event: MouseEvent): void {
  if (!canEdit.value) return;
  isResizingActive = true;
  resizeStartX = event.clientX;
  resizeStartY = event.clientY;
  const el = containerRef.value;
  resizeStartWidth = el?.offsetWidth ?? (localWidth.value ?? 240);
  resizeStartHeight = el?.offsetHeight ?? (localHeight.value ?? 180);
  document.addEventListener("mousemove", onResizeMove);
  document.addEventListener("mouseup", stopResize);
}

function onResizeMove(event: MouseEvent): void {
  const zoom = viewport.value.zoom || 1;
  const dx = (event.clientX - resizeStartX) / zoom;
  const dy = (event.clientY - resizeStartY) / zoom;
  localWidth.value = Math.max(MIN_WIDTH, resizeStartWidth + dx);
  localHeight.value = Math.max(MIN_HEIGHT, resizeStartHeight + dy);
}

function stopResize(): void {
  isResizingActive = false;
  document.removeEventListener("mousemove", onResizeMove);
  document.removeEventListener("mouseup", stopResize);
  workflowStore.updateNode(props.id, {
    stickyWidth: localWidth.value ?? undefined,
    stickyHeight: localHeight.value ?? undefined,
  });
}

onUnmounted(() => {
  document.removeEventListener("mousemove", onResizeMove);
  document.removeEventListener("mouseup", stopResize);
});
</script>

<template>
  <!-- eslint-disable vue/no-v-html -->
  <div
    ref="containerRef"
    :class="cn(
      'group flex flex-col min-w-[200px] rounded-lg border-2 px-4 py-3 shadow-md text-sm transition-colors',
      colorTheme.container,
      resizable ? 'relative overflow-visible' : 'max-w-[320px]',
      selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background'
    )"
    :style="containerStyle"
    @dblclick.stop="startNoteEditing"
    @mousemove="updatePaletteVisibility"
    @mouseleave="hidePaletteIfIdle"
  >
    <div
      :class="cn(
        'min-h-6 shrink-0 text-xs font-semibold uppercase tracking-wide',
        colorTheme.header
      )"
      @dblclick.stop="startTitleEditing"
    >
      <input
        v-if="isEditingTitle"
        ref="titleInputRef"
        v-model="localTitle"
        :class="cn(
          'nodrag w-full rounded-md border bg-white/55 px-2 py-1 text-xs font-semibold uppercase tracking-wide outline-none dark:bg-black/20',
          colorTheme.input
        )"
        @blur="stopTitleEditing"
        @keydown.enter.prevent="stopTitleEditing"
        @keydown.esc.prevent="stopTitleEditing"
      >
      <span v-else>{{ displayTitle }}</span>
    </div>
    <div
      :class="cn(
        'mt-2',
        resizable && hasExplicitSize ? 'flex-1 min-h-0 overflow-auto' : ''
      )"
    >
      <textarea
        v-if="isEditingNote"
        ref="textareaRef"
        v-model="localNote"
        :class="cn(
          'nodrag w-full rounded-md border bg-white/45 p-2 text-sm outline-none focus:ring-2 dark:bg-black/20 resize-none',
          colorTheme.input,
          resizable && hasExplicitSize ? 'h-full' : 'min-h-[120px]'
        )"
        @blur="stopNoteEditing"
        @keydown.esc.prevent="stopNoteEditing"
      />
      <div
        v-else
        class="sticky-note-content leading-relaxed"
        v-html="renderedNote"
      />
    </div>

    <div
      v-if="canEdit"
      class="nodrag absolute left-0 top-full z-10 h-[50px] w-full"
      @dblclick.stop
      @mousedown.stop
      @mouseenter="isPaletteVisible = true"
      @mousemove="isPaletteVisible = true"
      @mouseleave="hidePaletteIfIdle"
    />

    <div
      v-if="canEdit"
      :class="cn(
        'nodrag absolute left-1/2 top-[calc(100%+6px)] z-20 flex -translate-x-1/2 items-center justify-center gap-1.5 rounded-md border border-black/10 bg-white/80 px-2 py-1 shadow-sm backdrop-blur transition-opacity dark:border-white/10 dark:bg-black/45',
        shouldShowPalette ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      )"
      @dblclick.stop
      @mousedown.stop
      @mouseenter="isPaletteHovered = true"
      @mouseleave="isPaletteHovered = false; hidePaletteIfIdle()"
    >
      <button
        v-for="color in STICKY_COLORS"
        :key="color"
        type="button"
        :title="`Set ${color} color`"
        :aria-label="`Set ${color} sticky note color`"
        :class="cn(
          'h-4 w-4 rounded-full border border-black/15 shadow-sm transition-transform hover:scale-110 focus:outline-none focus:ring-2 focus:ring-primary',
          STICKY_COLOR_THEMES[color].swatch,
          color === currentColor && 'ring-2 ring-primary ring-offset-1 ring-offset-background'
        )"
        @mousedown.prevent.stop
        @click.stop="setColor(color)"
      />
    </div>

    <div
      v-if="resizable"
      class="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize flex items-end justify-end p-0.5 opacity-30 hover:opacity-70 transition-opacity"
      @mousedown.stop.prevent="startResize"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 8 8"
        :class="cn('w-3 h-3 fill-current', colorTheme.resize)"
      >
        <path d="M6 0L8 2L2 8L0 6L6 0zM8 4L8 8L4 8L8 4z" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.sticky-note-content :deep(p) {
  margin: 0 0 0.45rem;
}

.sticky-note-content :deep(p:last-child) {
  margin-bottom: 0;
}

.sticky-note-content :deep(h1),
.sticky-note-content :deep(h2),
.sticky-note-content :deep(h3) {
  margin: 0.45rem 0 0.25rem;
  font-weight: 700;
  line-height: 1.2;
}

.sticky-note-content :deep(h1) {
  font-size: 1.25rem;
}

.sticky-note-content :deep(h2) {
  font-size: 1.125rem;
}

.sticky-note-content :deep(h3) {
  font-size: 1rem;
}

.sticky-note-content :deep(a) {
  color: rgb(37 99 235);
  text-decoration: underline;
}

.sticky-note-content :deep(code) {
  border-radius: 0.25rem;
  background: rgb(0 0 0 / 0.1);
  padding: 0.125rem 0.25rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.75rem;
}

.sticky-note-content :deep(img) {
  display: block;
  max-width: 100%;
  max-height: 220px;
  border-radius: 0.375rem;
  object-fit: contain;
}

.sticky-note-content :deep(img + a),
.sticky-note-content :deep(p + p) {
  margin-top: 0.5rem;
}

:global(.dark) .sticky-note-content :deep(a) {
  color: rgb(96 165 250);
}

:global(.dark) .sticky-note-content :deep(code) {
  background: rgb(255 255 255 / 0.12);
}
</style>
