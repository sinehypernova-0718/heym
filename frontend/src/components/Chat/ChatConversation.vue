<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from "vue";
import { Send, Bot, User, Loader2, ChevronRight } from "lucide-vue-next";

import { credentialsApi } from "@/services/api";
import { useChatStore } from "@/stores/chat";
import type { CredentialListItem, LLMModel } from "@/types/credential";

interface Props {
  conversationId: string;
}

const props = defineProps<Props>();

const chatStore = useChatStore();

const input = ref("");
const messagesEndRef = ref<HTMLElement | null>(null);
const credentials = ref<CredentialListItem[]>([]);
const models = ref<LLMModel[]>([]);
const selectedCredentialId = ref("");
const selectedModel = ref("");
const isLoadingModels = ref(false);
const credentialError = ref("");

const messages = computed(() => chatStore.activeConversation?.messages ?? []);
const conversationTitle = computed(() => chatStore.activeConversation?.title ?? "");

onMounted(async () => {
  await loadCredentials();
  await chatStore.loadConversation(props.conversationId);
});

watch(
  () => props.conversationId,
  async (id) => {
    await chatStore.loadConversation(id);
  },
);

watch(messages, () => {
  nextTick(scrollToBottom);
});

watch(
  () => chatStore.streamingContent,
  () => {
    nextTick(scrollToBottom);
  },
);

function scrollToBottom(): void {
  messagesEndRef.value?.scrollIntoView({ behavior: "smooth" });
}

async function loadCredentials(): Promise<void> {
  try {
    credentials.value = await credentialsApi.listLLM();
    if (credentials.value.length > 0) {
      selectedCredentialId.value = credentials.value[0].id;
      await loadModels(selectedCredentialId.value);
    }
  } catch {
    credentialError.value = "Failed to load credentials";
  }
}

async function loadModels(credId: string): Promise<void> {
  if (!credId) return;
  isLoadingModels.value = true;
  models.value = [];
  selectedModel.value = "";
  try {
    models.value = await credentialsApi.getModels(credId);
    if (models.value.length > 0) {
      selectedModel.value = models.value[0].id;
    }
  } catch {
    // credential may not support model listing
  } finally {
    isLoadingModels.value = false;
  }
}

async function onCredentialChange(): Promise<void> {
  await loadModels(selectedCredentialId.value);
}

async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text || chatStore.isStreaming || !selectedCredentialId.value || !selectedModel.value) return;
  input.value = "";
  await chatStore.sendMessage(props.conversationId, text, selectedCredentialId.value, selectedModel.value);
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex items-center gap-2 px-4 py-3 border-b border-border/40 shrink-0">
      <button
        v-if="!chatStore.isSidebarOpen"
        class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        title="Open chat list"
        @click="chatStore.toggleSidebar"
      >
        <ChevronRight class="w-4 h-4" />
      </button>
      <h2 class="text-sm font-semibold truncate">
        {{ conversationTitle || 'Chat' }}
      </h2>
    </div>

    <div class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      <div
        v-if="chatStore.isLoadingMessages"
        class="flex justify-center py-8"
      >
        <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
      </div>

      <template v-else>
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start']"
        >
          <div
            v-if="msg.role === 'assistant'"
            class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5"
          >
            <Bot class="w-4 h-4 text-primary" />
          </div>

          <div
            :class="[
              'max-w-[72%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap',
              msg.role === 'user'
                ? 'bg-primary text-primary-foreground rounded-tr-sm'
                : 'bg-muted text-foreground rounded-tl-sm'
            ]"
          >
            {{ msg.content }}
          </div>

          <div
            v-if="msg.role === 'user'"
            class="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5"
          >
            <User class="w-4 h-4 text-muted-foreground" />
          </div>
        </div>

        <div
          v-if="chatStore.isStreaming && chatStore.streamingContent"
          class="flex gap-3 justify-start"
        >
          <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
            <Bot class="w-4 h-4 text-primary" />
          </div>
          <div class="max-w-[72%] rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed bg-muted text-foreground whitespace-pre-wrap">
            {{ chatStore.streamingContent }}<span class="inline-block w-0.5 h-4 bg-current ml-0.5 animate-pulse" />
          </div>
        </div>

        <div
          v-else-if="chatStore.isStreaming"
          class="flex gap-3 justify-start"
        >
          <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Bot class="w-4 h-4 text-primary" />
          </div>
          <div class="rounded-2xl rounded-tl-sm px-4 py-2.5 bg-muted">
            <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        </div>
      </template>

      <div ref="messagesEndRef" />
    </div>

    <div class="shrink-0 border-t border-border/40 px-4 py-3 space-y-2">
      <div class="flex gap-2">
        <select
          v-model="selectedCredentialId"
          class="text-xs border border-border rounded-md px-2 py-1 bg-background text-foreground"
          @change="onCredentialChange"
        >
          <option
            v-if="credentials.length === 0"
            value=""
          >
            No LLM credentials
          </option>
          <option
            v-for="cred in credentials"
            :key="cred.id"
            :value="cred.id"
          >
            {{ cred.name }}
          </option>
        </select>

        <select
          v-model="selectedModel"
          class="text-xs border border-border rounded-md px-2 py-1 bg-background text-foreground flex-1"
          :disabled="isLoadingModels || models.length === 0"
        >
          <option
            v-if="isLoadingModels"
            value=""
          >
            Loading…
          </option>
          <option
            v-else-if="models.length === 0"
            value=""
          >
            No models
          </option>
          <option
            v-for="m in models"
            :key="m.id"
            :value="m.id"
          >
            {{ m.id }}
          </option>
        </select>
      </div>

      <div class="flex gap-2">
        <textarea
          v-model="input"
          rows="1"
          placeholder="Message…"
          class="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-shadow max-h-40"
          :disabled="chatStore.isStreaming"
          @keydown="onKeydown"
          @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = ($event.target as HTMLTextAreaElement).scrollHeight + 'px'"
        />
        <button
          :disabled="!input.trim() || chatStore.isStreaming || !selectedCredentialId || !selectedModel"
          class="self-end p-2.5 rounded-xl bg-primary text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors"
          @click="send"
        >
          <Send class="w-4 h-4" />
        </button>
      </div>
      <p
        v-if="credentialError"
        class="text-xs text-destructive"
      >
        {{ credentialError }}
      </p>
    </div>
  </div>
</template>
