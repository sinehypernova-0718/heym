<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@vue-flow/core";
import type { EdgeProps } from "@vue-flow/core";
import { Plus, Trash2 } from "lucide-vue-next";

import { useWorkflowStore } from "@/stores/workflow";

interface EdgeActionData {
  allowDelete?: boolean;
  allowInsert?: boolean;
}

const props = defineProps<EdgeProps>();

const workflowStore = useWorkflowStore();
const isHovered = ref(false);
const edgeActionData = computed(() => props.data as EdgeActionData | undefined);
const canDelete = computed(() => edgeActionData.value?.allowDelete !== false);
const canInsert = computed(() => edgeActionData.value?.allowInsert !== false);
const hasActions = computed(() => canDelete.value || canInsert.value);

const path = computed(() => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });

  return { edgePath, labelX, labelY };
});

function handleInsertClick(event: MouseEvent): void {
  if (!canInsert.value) return;
  event.stopPropagation();

  workflowStore.setPendingInsertEdge({
    edgeId: props.id,
    sourceId: props.source,
    targetId: props.target,
    sourceHandle: props.sourceHandleId || undefined,
    targetHandle: props.targetHandleId || undefined,
  });

  workflowStore.clearNodeSearchQuery();
}

function handleDeleteClick(event: MouseEvent): void {
  if (!canDelete.value) return;
  event.stopPropagation();

  workflowStore.removeEdge(props.id);
}

function onEdgeMouseEnter(): void {
  isHovered.value = true;
}

function onEdgeMouseLeave(): void {
  isHovered.value = false;
}

onMounted(() => {
  const edgeEl = document.querySelector(`[data-id="${props.id}"]`);
  if (edgeEl) {
    edgeEl.addEventListener("mouseenter", onEdgeMouseEnter);
    edgeEl.addEventListener("mouseleave", onEdgeMouseLeave);
  }
});

onUnmounted(() => {
  const edgeEl = document.querySelector(`[data-id="${props.id}"]`);
  if (edgeEl) {
    edgeEl.removeEventListener("mouseenter", onEdgeMouseEnter);
    edgeEl.removeEventListener("mouseleave", onEdgeMouseLeave);
  }
});
</script>

<template>
  <BaseEdge
    :id="id"
    :style="style"
    :path="path.edgePath"
    :marker-end="markerEnd"
    :interaction-width="20"
  />
  <EdgeLabelRenderer>
    <div
      v-if="hasActions"
      class="edge-actions-wrapper nodrag nopan"
      :class="{ 'is-visible': isHovered }"
      :style="{
        transform: `translate(-50%, -50%) translate(${path.labelX}px, ${path.labelY}px)`,
        pointerEvents: 'all',
      }"
      @pointerdown.stop
      @dblclick.stop
      @mouseenter="isHovered = true"
      @mouseleave="isHovered = false"
    >
      <button
        v-if="canInsert"
        class="edge-action-button insert-button"
        type="button"
        aria-label="Insert node between"
        title="Insert node"
        @click="handleInsertClick"
      >
        <Plus class="w-3 h-3" />
      </button>
      <button
        v-if="canDelete"
        class="edge-action-button delete-button"
        type="button"
        aria-label="Delete connection"
        title="Delete connection"
        @click="handleDeleteClick"
      >
        <Trash2 class="w-3 h-3" />
      </button>
    </div>
  </EdgeLabelRenderer>
</template>

<style scoped>
.edge-actions-wrapper {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.edge-actions-wrapper.is-visible {
  opacity: 1;
}

.edge-action-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
  border: 2px solid hsl(var(--background));
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.edge-action-button:hover {
  transform: scale(1.2);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.insert-button {
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
}

.delete-button {
  background: hsl(var(--destructive));
  color: hsl(var(--destructive-foreground));
}
</style>
