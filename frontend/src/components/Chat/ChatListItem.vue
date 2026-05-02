<script setup lang="ts">
import { ref } from "vue";
import { Pin, PinOff, Pencil, Trash2, Check, X } from "lucide-vue-next";

import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface Props {
  conversation: Conversation;
  isActive: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  select: [id: string];
  rename: [id: string, title: string];
  togglePin: [id: string];
  delete: [id: string];
}>();

const isEditing = ref(false);
const editTitle = ref("");
const isConfirmingDelete = ref(false);

function startEdit(): void {
  editTitle.value = props.conversation.title;
  isEditing.value = true;
}

function commitEdit(): void {
  const trimmed = editTitle.value.trim();
  if (trimmed && trimmed !== props.conversation.title) {
    emit("rename", props.conversation.id, trimmed);
  }
  isEditing.value = false;
}

function cancelEdit(): void {
  isEditing.value = false;
}

function onEditKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter") commitEdit();
  if (e.key === "Escape") cancelEdit();
}

function confirmDelete(): void {
  isConfirmingDelete.value = true;
}

function doDelete(): void {
  emit("delete", props.conversation.id);
  isConfirmingDelete.value = false;
}

function cancelDelete(): void {
  isConfirmingDelete.value = false;
}
</script>

<template>
  <div
    :class="cn(
      'group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors',
      isActive
        ? 'bg-primary/10 text-primary'
        : 'hover:bg-muted/60 text-foreground'
    )"
    @click="emit('select', conversation.id)"
  >
    <Pin
      v-if="conversation.is_pinned"
      class="w-3 h-3 shrink-0 text-primary opacity-60"
    />

    <div class="flex-1 min-w-0">
      <template v-if="isEditing">
        <input
          v-model="editTitle"
          class="w-full text-sm bg-background border border-border rounded px-1 py-0.5 outline-none"
          autofocus
          @keydown="onEditKeydown"
          @blur="commitEdit"
          @click.stop
        >
      </template>
      <template v-else>
        <span class="block text-sm truncate leading-5">{{ conversation.title }}</span>
      </template>
    </div>

    <div
      v-if="!isEditing && !isConfirmingDelete"
      class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
      @click.stop
    >
      <button
        class="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
        :title="conversation.is_pinned ? 'Unpin' : 'Pin to top'"
        @click="emit('togglePin', conversation.id)"
      >
        <PinOff
          v-if="conversation.is_pinned"
          class="w-3.5 h-3.5"
        />
        <Pin
          v-else
          class="w-3.5 h-3.5"
        />
      </button>
      <button
        class="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
        title="Rename"
        @click="startEdit"
      >
        <Pencil class="w-3.5 h-3.5" />
      </button>
      <button
        class="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
        title="Delete"
        @click="confirmDelete"
      >
        <Trash2 class="w-3.5 h-3.5" />
      </button>
    </div>

    <div
      v-if="isConfirmingDelete"
      class="flex items-center gap-0.5"
      @click.stop
    >
      <button
        class="p-1 rounded bg-destructive/10 text-destructive hover:bg-destructive/20"
        title="Confirm delete"
        @click="doDelete"
      >
        <Check class="w-3.5 h-3.5" />
      </button>
      <button
        class="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
        title="Cancel"
        @click="cancelDelete"
      >
        <X class="w-3.5 h-3.5" />
      </button>
    </div>
  </div>
</template>
