<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useVueFlow } from "@vue-flow/core";

import type { NodeData } from "@/types/workflow";

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

const isEditing = ref(false);
const localNote = ref(props.data.note || "");
const textareaRef = ref<HTMLTextAreaElement | null>(null);
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
    if (!isEditing.value) {
      localNote.value = value || "";
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

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  return "#";
}

function renderMarkdown(raw: string): string {
  const safe = escapeHtml(raw);
  const lines = safe.split("\n");
  const result: string[] = [];
  let currentParagraph: string[] = [];

  function flushParagraph(): void {
    if (currentParagraph.length > 0) {
      result.push(`<p>${currentParagraph.join("<br />")}</p>`);
      currentParagraph = [];
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "") {
      flushParagraph();
      continue;
    }

    if (trimmed.startsWith("### ")) {
      flushParagraph();
      result.push(`<h3 class="text-base font-bold mt-2 mb-1">${trimmed.slice(4)}</h3>`);
    } else if (trimmed.startsWith("## ")) {
      flushParagraph();
      result.push(`<h2 class="text-lg font-bold mt-2 mb-1">${trimmed.slice(3)}</h2>`);
    } else if (trimmed.startsWith("# ")) {
      flushParagraph();
      result.push(`<h1 class="text-xl font-bold mt-2 mb-1">${trimmed.slice(2)}</h1>`);
    } else {
      let processed = line
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/`(.+?)`/g, "<code class=\"px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 font-mono text-xs\">$1</code>")
        .replace(/\[([^\]]+)]\(([^)]+)\)/g, (_match, text, url) => {
          const safeUrl = sanitizeUrl(url);
          return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 underline">${text}</a>`;
        });
      currentParagraph.push(processed);
    }
  }

  flushParagraph();
  return result.join("");
}

const renderedNote = computed(() => {
  const value = (props.data.note || "").trim();
  const content = value.length > 0 ? value : "Double click to edit";
  return renderMarkdown(content);
});

function startEditing(): void {
  isEditing.value = true;
  localNote.value = props.data.note || "";
  nextTick(() => textareaRef.value?.focus());
}

function stopEditing(): void {
  isEditing.value = false;
  workflowStore.updateNode(props.id, { note: localNote.value });
}

function startResize(event: MouseEvent): void {
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
      'flex flex-col min-w-[200px] rounded-lg border-2 bg-yellow-100/80 dark:bg-yellow-900/30 border-yellow-300 dark:border-yellow-700 px-4 py-3 shadow-md text-sm text-yellow-900 dark:text-yellow-100',
      resizable ? 'relative overflow-hidden' : 'max-w-[320px]',
      selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background'
    )"
    :style="containerStyle"
    @dblclick.stop="startEditing"
  >
    <div class="text-xs font-semibold uppercase tracking-wide text-yellow-800/80 dark:text-yellow-200/80 shrink-0">
      Sticky Note
    </div>
    <div
      :class="cn(
        'mt-2',
        resizable && hasExplicitSize ? 'flex-1 min-h-0 overflow-auto' : ''
      )"
    >
      <textarea
        v-if="isEditing"
        ref="textareaRef"
        v-model="localNote"
        :class="cn(
          'w-full bg-transparent border border-yellow-300/60 dark:border-yellow-700/60 rounded-md p-2 text-sm focus:outline-none focus:ring-2 focus:ring-yellow-400 resize-none',
          resizable && hasExplicitSize ? 'h-full' : 'min-h-[120px]'
        )"
        @blur="stopEditing"
      />
      <div
        v-else
        class="space-y-1 leading-relaxed"
        v-html="renderedNote"
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
        class="w-3 h-3 fill-current text-yellow-800 dark:text-yellow-200"
      >
        <path d="M6 0L8 2L2 8L0 6L6 0zM8 4L8 8L4 8L8 4z" />
      </svg>
    </div>
  </div>
</template>
