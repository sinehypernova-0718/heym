<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { SquarePen, ChevronRight, MessageCircle } from "lucide-vue-next";

import AppHeader from "@/components/Layout/AppHeader.vue";
import DashboardNav from "@/components/Layout/DashboardNav.vue";
import WorkspaceShell from "@/components/Layout/WorkspaceShell.vue";
import ChatListPanel from "@/components/Chat/ChatListPanel.vue";
import ChatConversation from "@/components/Chat/ChatConversation.vue";
import { useChatStore } from "@/stores/chat";

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();

const conversationId = computed(() => route.params.id as string | undefined);

async function createNew(): Promise<void> {
  const conv = await chatStore.createConversation();
  router.push(`/chats/${conv.id}`);
}
</script>

<template>
  <WorkspaceShell>
    <div class="h-screen flex flex-col bg-background overflow-hidden">
      <AppHeader>
        <template #actions>
          <button
            v-if="!chatStore.isSidebarOpen"
            class="p-2 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Open chat list"
            @click="chatStore.toggleSidebar"
          >
            <ChevronRight class="w-4 h-4" />
          </button>
        </template>
      </AppHeader>

      <main class="dashboard-main flex-1 flex flex-col min-h-0 overflow-hidden px-3 sm:px-4 py-4 sm:py-6 md:py-8">
        <div class="absolute top-0 left-0 right-0 h-[500px] pointer-events-none overflow-hidden">
          <div class="absolute inset-0 bg-gradient-to-b from-primary/[0.03] via-transparent to-transparent" />
          <div class="absolute inset-0 bg-dots-pattern opacity-30" />
        </div>

        <div class="w-full max-w-7xl mx-auto relative flex-1 flex flex-col min-h-0">
          <DashboardNav />

          <div class="flex flex-1 min-h-0 rounded-2xl border border-border/50 bg-card/60 overflow-hidden shadow-sm">
            <ChatListPanel
              v-if="chatStore.isSidebarOpen"
              :active-conversation-id="conversationId"
            />

            <div class="flex-1 flex flex-col min-w-0 h-full">
              <ChatConversation
                v-if="conversationId"
                :conversation-id="conversationId"
              />

              <div
                v-else
                class="flex-1 flex flex-col items-center justify-center gap-4 text-muted-foreground"
              >
                <MessageCircle class="w-12 h-12 opacity-20" />
                <p class="text-sm">
                  Select a conversation or start a new one
                </p>
                <button
                  class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                  @click="createNew"
                >
                  <SquarePen class="w-4 h-4" />
                  New Chat
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </WorkspaceShell>
</template>
