<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { SquarePen, ChevronRight, Send } from "lucide-vue-next";

import AppHeader from "@/components/Layout/AppHeader.vue";
import DashboardNav from "@/components/Layout/DashboardNav.vue";
import WorkspaceShell from "@/components/Layout/WorkspaceShell.vue";
import ChatListPanel from "@/components/Chat/ChatListPanel.vue";
import ChatConversation from "@/components/Chat/ChatConversation.vue";
import type { ShowcaseContext } from "@/features/showcase/showcase.types";
import { hasShowcaseChatDraftPending } from "@/features/showcase/showcaseChatDraft";
import { useChatStore } from "@/stores/chat";

const chatsShowcaseContext: ShowcaseContext = "dashboard:chat";

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();

const conversationId = computed(() => route.params.id as string | undefined);
const isCreateNewCoolingDown = ref(false);
let createNewCooldownTimeout: ReturnType<typeof setTimeout> | null = null;

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

onMounted(() => {
  if (!conversationId.value && hasShowcaseChatDraftPending()) {
    void createNew();
  }
});

onUnmounted(() => {
  if (createNewCooldownTimeout) clearTimeout(createNewCooldownTimeout);
});
</script>

<template>
  <WorkspaceShell :showcase-context="chatsShowcaseContext">
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

          <div class="relative flex flex-1 min-h-0 rounded-2xl border border-border/50 bg-card/60 overflow-hidden shadow-sm">
            <div
              v-if="!chatStore.isSidebarOpen"
              class="absolute left-0 top-0 z-20 h-full w-6"
              aria-hidden="true"
              @mouseenter="chatStore.openSidebar"
            />

            <div
              class="chat-sidebar-shell"
              :class="{ 'chat-sidebar-shell--closed': !chatStore.isSidebarOpen }"
              :aria-hidden="!chatStore.isSidebarOpen"
            >
              <ChatListPanel
                class="chat-sidebar-panel"
                :class="{ 'chat-sidebar-panel--closed': !chatStore.isSidebarOpen }"
                :active-conversation-id="conversationId"
              />
            </div>

            <div class="flex-1 flex flex-col min-w-0 h-full">
              <ChatConversation
                v-if="conversationId"
                :conversation-id="conversationId"
              />

              <div
                v-else
                class="flex-1 flex flex-col items-center justify-center gap-4 text-muted-foreground"
              >
                <Send class="w-10 h-10 sm:w-12 sm:h-12 opacity-50" />
                <p class="text-xs sm:text-sm max-w-[280px] sm:max-w-none text-center">
                  Ask to run a workflow, list workflows, or ask about your data.
                </p>
                <button
                  class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50 transition-colors"
                  :disabled="isCreateNewCoolingDown"
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

<style scoped>
.chat-sidebar-shell {
  width: 16rem;
  overflow: hidden;
  flex-shrink: 0;
  transition: width 240ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: width;
}

.chat-sidebar-shell--closed {
  width: 0;
}

.chat-sidebar-panel {
  transform: translate3d(0, 0, 0);
  opacity: 1;
  transition:
    transform 240ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 160ms ease-out;
  will-change: transform, opacity;
}

.chat-sidebar-panel--closed {
  pointer-events: none;
  transform: translate3d(-18px, 0, 0);
  opacity: 0;
}
</style>
