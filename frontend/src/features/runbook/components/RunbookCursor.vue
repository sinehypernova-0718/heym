<script setup lang="ts">
import { runbookCursor } from "@/features/runbook/useRunbookPlayer";
</script>

<template>
  <Teleport to="body">
    <div
      v-if="runbookCursor.visible"
      class="runbook-cursor"
      :style="{ left: `${runbookCursor.x}px`, top: `${runbookCursor.y}px` }"
      aria-hidden="true"
    >
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
      >
        <path
          d="M5 3l14 7-6 1.5L9.5 18 5 3z"
          fill="white"
          stroke="black"
          stroke-width="1.2"
          stroke-linejoin="round"
        />
      </svg>
    </div>
  </Teleport>
</template>
