import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { chatApi } from "@/services/api";
import type { Conversation, ConversationDetail, Message } from "@/types/chat";

const SIDEBAR_OPEN_KEY = "heym-chat-sidebar-open";

export const useChatStore = defineStore("chat", () => {
  const conversations = ref<Conversation[]>([]);
  const activeConversation = ref<ConversationDetail | null>(null);
  const isSidebarOpen = ref(
    typeof window !== "undefined"
      ? window.localStorage.getItem(SIDEBAR_OPEN_KEY) !== "false"
      : true,
  );
  const isLoadingConversations = ref(false);
  const isLoadingMessages = ref(false);
  const isStreaming = ref(false);
  const streamingContent = ref("");

  const sortedConversations = computed<Conversation[]>(() =>
    [...conversations.value].sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    }),
  );

  function toggleSidebar(): void {
    isSidebarOpen.value = !isSidebarOpen.value;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SIDEBAR_OPEN_KEY, String(isSidebarOpen.value));
    }
  }

  async function loadConversations(): Promise<void> {
    isLoadingConversations.value = true;
    try {
      conversations.value = await chatApi.listConversations();
    } finally {
      isLoadingConversations.value = false;
    }
  }

  async function loadConversation(id: string): Promise<void> {
    isLoadingMessages.value = true;
    try {
      activeConversation.value = await chatApi.getConversation(id);
    } finally {
      isLoadingMessages.value = false;
    }
  }

  async function createConversation(title?: string): Promise<Conversation> {
    const conv = await chatApi.createConversation(title ? { title } : {});
    conversations.value = [conv, ...conversations.value];
    return conv;
  }

  async function renameConversation(id: string, title: string): Promise<void> {
    const updated = await chatApi.updateConversation(id, { title });
    _patchConversation(updated);
    if (activeConversation.value?.id === id) {
      activeConversation.value = { ...activeConversation.value, title: updated.title };
    }
  }

  async function togglePin(id: string): Promise<void> {
    const conv = conversations.value.find((c) => c.id === id);
    if (!conv) return;
    const updated = await chatApi.updateConversation(id, { is_pinned: !conv.is_pinned });
    _patchConversation(updated);
  }

  async function deleteConversation(id: string): Promise<void> {
    await chatApi.deleteConversation(id);
    conversations.value = conversations.value.filter((c) => c.id !== id);
    if (activeConversation.value?.id === id) {
      activeConversation.value = null;
    }
  }

  async function sendMessage(
    conversationId: string,
    content: string,
    credentialId: string,
    model: string,
  ): Promise<void> {
    if (!activeConversation.value || activeConversation.value.id !== conversationId) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    activeConversation.value = {
      ...activeConversation.value,
      messages: [...activeConversation.value.messages, userMessage],
    };

    isStreaming.value = true;
    streamingContent.value = "";

    await chatApi.streamMessagePost(
      conversationId,
      content,
      credentialId,
      model,
      (text) => {
        streamingContent.value += text;
      },
      () => {
        const assistantMessage: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: streamingContent.value,
          created_at: new Date().toISOString(),
        };
        if (activeConversation.value) {
          activeConversation.value = {
            ...activeConversation.value,
            messages: [...activeConversation.value.messages, assistantMessage],
          };
        }
        streamingContent.value = "";
        isStreaming.value = false;
        _refreshConversationTimestamp(conversationId);
      },
      (_err) => {
        isStreaming.value = false;
        streamingContent.value = "";
      },
    );
  }

  function _patchConversation(updated: Conversation): void {
    conversations.value = conversations.value.map((c) => (c.id === updated.id ? updated : c));
  }

  function _refreshConversationTimestamp(id: string): void {
    conversations.value = conversations.value.map((c) =>
      c.id === id ? { ...c, updated_at: new Date().toISOString() } : c,
    );
  }

  return {
    conversations,
    sortedConversations,
    activeConversation,
    isSidebarOpen,
    isLoadingConversations,
    isLoadingMessages,
    isStreaming,
    streamingContent,
    toggleSidebar,
    loadConversations,
    loadConversation,
    createConversation,
    renameConversation,
    togglePin,
    deleteConversation,
    sendMessage,
  };
});
