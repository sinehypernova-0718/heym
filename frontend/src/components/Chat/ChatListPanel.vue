<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { SquarePen, ChevronLeft, Trash2, Check, X } from "lucide-vue-next";

import { useChatStore } from "@/stores/chat";
import ChatListItem from "@/components/Chat/ChatListItem.vue";

interface Props {
  activeConversationId?: string;
}

const props = defineProps<Props>();

const router = useRouter();
const chatStore = useChatStore();
const isConfirmingClearAll = ref(false);
const isCreateNewCoolingDown = ref(false);
const confirmClearAllButtonRef = ref<HTMLButtonElement | null>(null);
let createNewCooldownTimeout: ReturnType<typeof setTimeout> | null = null;

onMounted(() => {
  chatStore.loadConversations();
});

async function createNew(): Promise<void> {
  if (isCreateNewCoolingDown.value) return;
  isCreateNewCoolingDown.value = true;
  createNewCooldownTimeout = setTimeout(() => {
    isCreateNewCoolingDown.value = false;
    createNewCooldownTimeout = null;
  }, 2000);
  try {
    const conv = await chatStore.createConversation();
    router.push(`/chats/${conv.id}`);
  } catch {
    if (createNewCooldownTimeout) clearTimeout(createNewCooldownTimeout);
    createNewCooldownTimeout = null;
    isCreateNewCoolingDown.value = false;
  }
}

function select(id: string): void {
  router.push(`/chats/${id}`);
}

async function deleteConversation(id: string): Promise<void> {
  await chatStore.deleteConversation(id);
  if (id === props.activeConversationId) {
    router.push("/chats");
  }
}

function confirmClearAll(): void {
  isConfirmingClearAll.value = true;
  nextTick(() => {
    confirmClearAllButtonRef.value?.focus();
  });
}

async function clearAll(): Promise<void> {
  await chatStore.clearConversations();
  isConfirmingClearAll.value = false;
  router.push("/chats");
}

function cancelClearAll(): void {
  isConfirmingClearAll.value = false;
}

onUnmounted(() => {
  if (createNewCooldownTimeout) clearTimeout(createNewCooldownTimeout);
});
</script>

<template>
  <aside class="flex flex-col h-full w-64 shrink-0 border-r border-border/50 bg-card/40">
    <div class="flex items-center justify-between px-3 py-3 border-b border-border/40">
      <span class="text-sm font-semibold text-foreground">Chats</span>
      <div class="flex items-center gap-1">
        <template v-if="isConfirmingClearAll">
          <button
            ref="confirmClearAllButtonRef"
            type="button"
            class="p-1.5 rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
            title="Confirm clear all"
            @click="clearAll"
          >
            <Check class="w-4 h-4" />
          </button>
          <button
            type="button"
            class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Cancel"
            @click="cancelClearAll"
          >
            <X class="w-4 h-4" />
          </button>
        </template>
        <button
          v-else
          class="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive disabled:pointer-events-none disabled:opacity-40 transition-colors"
          title="Clear all chats"
          :disabled="chatStore.sortedConversations.length === 0"
          @click="confirmClearAll"
        >
          <Trash2 class="w-4 h-4" />
        </button>
        <button
          class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground disabled:pointer-events-none disabled:opacity-50 transition-colors"
          title="New chat"
          :disabled="isCreateNewCoolingDown"
          @click="createNew"
        >
          <SquarePen class="w-4 h-4" />
        </button>
        <button
          class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title="Close panel"
          @click="chatStore.toggleSidebar"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
      <div
        v-if="chatStore.isLoadingConversations && chatStore.sortedConversations.length === 0"
        class="px-3 py-4 text-sm text-muted-foreground text-center"
      >
        Loading…
      </div>
      <div
        v-else-if="chatStore.sortedConversations.length === 0"
        class="px-3 py-4 text-sm text-muted-foreground text-center"
      >
        No conversations yet
      </div>
      <ChatListItem
        v-for="conv in chatStore.sortedConversations"
        :key="conv.id"
        :conversation="conv"
        :is-active="conv.id === activeConversationId"
        @select="select"
        @rename="chatStore.renameConversation"
        @toggle-pin="chatStore.togglePin"
        @delete="deleteConversation"
      />
    </div>
  </aside>
</template>
