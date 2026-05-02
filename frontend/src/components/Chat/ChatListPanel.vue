<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { SquarePen, ChevronLeft } from "lucide-vue-next";

import { useChatStore } from "@/stores/chat";
import ChatListItem from "@/components/Chat/ChatListItem.vue";

interface Props {
  activeConversationId?: string;
}

defineProps<Props>();

const router = useRouter();
const chatStore = useChatStore();

onMounted(() => {
  chatStore.loadConversations();
});

async function createNew(): Promise<void> {
  const conv = await chatStore.createConversation();
  router.push(`/chats/${conv.id}`);
}

function select(id: string): void {
  router.push(`/chats/${id}`);
}
</script>

<template>
  <aside class="flex flex-col h-full w-64 shrink-0 border-r border-border/50 bg-card/40">
    <div class="flex items-center justify-between px-3 py-3 border-b border-border/40">
      <span class="text-sm font-semibold text-foreground">Chats</span>
      <div class="flex items-center gap-1">
        <button
          class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title="New chat"
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
        @delete="chatStore.deleteConversation"
      />
    </div>
  </aside>
</template>
