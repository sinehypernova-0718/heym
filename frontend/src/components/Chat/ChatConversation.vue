<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import {
  Send,
  Bot,
  Loader2,
  ChevronRight,
  ChevronDown,
  Copy,
  Check,
  ExternalLink,
  Square,
  Mic,
  MicOff,
  Paperclip,
  X,
} from "lucide-vue-next";
import { marked } from "marked";
import DOMPurify from "dompurify";

import type { Message } from "@/types/chat";
import type { CredentialListItem, LLMModel } from "@/types/credential";
import ReadonlyCanvasSurface from "@/components/Canvas/ReadonlyCanvasSurface.vue";
import Button from "@/components/ui/Button.vue";
import ImageLightbox from "@/components/ui/ImageLightbox.vue";
import { aiApi, credentialsApi } from "@/services/api";
import { useFileAttachment } from "@/composables/useFileAttachment";
import type { AttachedFile } from "@/composables/useFileAttachment";
import {
  consumeShowcaseChatDraft,
  SHOWCASE_CHAT_DRAFT_EVENT,
} from "@/features/showcase/showcaseChatDraft";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";

interface Props {
  conversationId: string;
}

const props = defineProps<Props>();

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const chatStore = useChatStore();
const authStore = useAuthStore();
const router = useRouter();

const input = ref("");
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const messagesEndRef = ref<HTMLElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const credentials = ref<CredentialListItem[]>([]);
const models = ref<LLMModel[]>([]);
const selectedCredentialId = ref("");
const selectedModel = ref("");
const isLoadingModels = ref(false);
const credentialError = ref("");
const modelsLoadFailed = ref(false);
const copiedMessageId = ref<string | null>(null);
const speechRecognition = ref<SpeechRecognition | null>(null);
const isSpeechSupported = ref(false);
const isListening = ref(false);
const isFixingTranscription = ref(false);
const imageLightboxSrc = ref<string | null>(null);
let copiedMessageIdTimeout: ReturnType<typeof setTimeout> | null = null;

interface SpeechRecognitionResultAlternative {
  transcript: string;
}

interface SpeechRecognitionResultItem {
  isFinal: boolean;
  0: SpeechRecognitionResultAlternative;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResultItem;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface SpeechRecognitionWindow extends Window {
  webkitSpeechRecognition?: new () => SpeechRecognition;
  SpeechRecognition?: new () => SpeechRecognition;
}

const { attachedFile, attachmentError, attachmentLoading, processFile, clearAttachment } =
  useFileAttachment();

const isShowingConversation = computed(
  () => chatStore.activeConversation?.id === props.conversationId,
);
const isTitleLoading = computed(() => !isShowingConversation.value);
const isConversationTransitioning = computed(
  () => chatStore.activeConversation !== null && !isShowingConversation.value,
);
const messages = computed(() => chatStore.activeConversation?.messages ?? []);
const conversationTitle = computed(() =>
  chatStore.activeConversation?.title ?? "",
);
const canSendMessage = computed(() => isShowingConversation.value && !isConversationTransitioning.value);
const canFocusInput = computed(
  () =>
    canSendMessage.value &&
    !chatStore.isStreaming &&
    !isLoadingModels.value &&
    !modelsLoadFailed.value &&
    Boolean(selectedCredentialId.value) &&
    Boolean(selectedModel.value),
);
const userInitial = computed(() => {
  const source = authStore.user?.name?.trim() || authStore.user?.email?.trim() || "?";
  return source.charAt(0).toUpperCase();
});

watch(
  () => props.conversationId,
  (id) => {
    void loadConversationForRoute(id);
    applyShowcaseDraft();
    focusInputWhenReady();
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

watch(
  canFocusInput,
  (canFocus) => {
    if (canFocus) {
      focusInputWhenReady();
    }
  },
);

watch(
  () => chatStore.activeConversation?.id,
  () => {
    focusInputWhenReady();
  },
);

function scrollToBottom(): void {
  messagesEndRef.value?.scrollIntoView({ behavior: "smooth" });
}

function focusInputWhenReady(): void {
  nextTick(() => {
    if (canFocusInput.value) {
      chatInputRef.value?.focus();
    }
  });
}

function applyShowcaseDraft(): void {
  const draft = consumeShowcaseChatDraft();
  if (!draft) return;
  input.value = draft;
  focusInputWhenReady();
}

async function loadConversationForRoute(id: string): Promise<void> {
  if (!UUID_PATTERN.test(id)) {
    await router.replace("/chats");
    return;
  }

  const result = await chatStore.loadConversation(id);
  if (result === "not_found" && props.conversationId === id) {
    await router.replace("/chats");
  }
}

onMounted(() => {
  setupSpeechRecognition();
  void loadConversationForRoute(props.conversationId);
  void loadCredentials();
  window.addEventListener(SHOWCASE_CHAT_DRAFT_EVENT, applyShowcaseDraft);
  applyShowcaseDraft();
  focusInputWhenReady();
});

function renderMarkdown(content: string): string {
  if (!content) return "";
  const html = marked(content, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
      "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "hr",
      "table", "thead", "tbody", "tr", "th", "td", "img", "video", "source",
    ],
    ALLOWED_ATTR: [
      "href", "target", "rel", "src", "alt", "controls", "playsinline",
      "muted", "loop", "preload", "type", "style",
    ],
  });
}

function handleMarkdownImageClick(event: MouseEvent): void {
  const target = event.target as HTMLElement;
  if (target.tagName === "IMG") {
    imageLightboxSrc.value = (target as HTMLImageElement).src;
  }
}

async function copyMessage(msg: Message): Promise<void> {
  if (!msg.content) return;
  try {
    await navigator.clipboard.writeText(msg.content);
    copiedMessageId.value = msg.id;
    if (copiedMessageIdTimeout) clearTimeout(copiedMessageIdTimeout);
    copiedMessageIdTimeout = setTimeout(() => {
      copiedMessageId.value = null;
    }, 1600);
  } catch {
    // ignore clipboard errors
  }
}

function openFilePicker(): void {
  fileInputRef.value?.click();
}

async function handleFileInputChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  await processFile(file);
  target.value = "";
}

function setupSpeechRecognition(): void {
  const recognitionWindow = window as SpeechRecognitionWindow;
  const SpeechRecognitionConstructor =
    recognitionWindow.SpeechRecognition || recognitionWindow.webkitSpeechRecognition;
  if (!SpeechRecognitionConstructor) {
    isSpeechSupported.value = false;
    return;
  }
  isSpeechSupported.value = true;
  const recognition = new SpeechRecognitionConstructor();
  recognition.lang = "tr-TR";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (event: SpeechRecognitionEvent) => {
    const transcripts = Array.from(event.results).map((result) => result[0]?.transcript ?? "");
    const transcript = transcripts.join("").trim();
    if (transcript) {
      input.value = transcript;
    }
  };
  recognition.onerror = () => {
    isListening.value = false;
  };
  recognition.onend = () => {
    if (isListening.value && speechRecognition.value) {
      speechRecognition.value.start();
    } else {
      isListening.value = false;
    }
  };
  speechRecognition.value = recognition;
}

async function fixTranscriptionIfNeeded(): Promise<void> {
  const text = input.value.trim();
  if (!text || !selectedCredentialId.value || !selectedModel.value) return;

  isFixingTranscription.value = true;
  try {
    const response = await aiApi.fixTranscription({
      credentialId: selectedCredentialId.value,
      model: selectedModel.value,
      text,
    });
    input.value = response.fixed_text;
  } catch {
    // keep original text
  } finally {
    isFixingTranscription.value = false;
  }
}

function toggleSpeechInput(): void {
  if (!speechRecognition.value) return;
  if (isListening.value) {
    isListening.value = false;
    speechRecognition.value.stop();
    fixTranscriptionIfNeeded();
    return;
  }
  input.value = "";
  isListening.value = true;
  speechRecognition.value.start();
}

async function loadCredentials(): Promise<void> {
  try {
    credentials.value = await credentialsApi.listLLM();
    if (credentials.value.length > 0 && !selectedCredentialId.value) {
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
  modelsLoadFailed.value = false;
  models.value = [];
  selectedModel.value = "";
  try {
    models.value = await credentialsApi.getModels(credId);
    if (models.value.length > 0) {
      selectedModel.value = models.value[models.value.length - 1].id;
    }
  } catch {
    modelsLoadFailed.value = true;
  } finally {
    isLoadingModels.value = false;
    focusInputWhenReady();
  }
}

async function onCredentialChange(): Promise<void> {
  await loadModels(selectedCredentialId.value);
}

async function send(): Promise<void> {
  const text = input.value.trim();
  if (
    !text ||
    chatStore.isStreaming ||
    !canSendMessage.value ||
    !selectedCredentialId.value ||
    !selectedModel.value ||
    modelsLoadFailed.value ||
    attachmentError.value !== null ||
    attachmentLoading.value
  ) {
    return;
  }
  input.value = "";
  const payloadAttachment: AttachedFile | null = attachedFile.value;
  clearAttachment();
  await chatStore.sendMessage(
    props.conversationId,
    text,
    selectedCredentialId.value,
    selectedModel.value,
    payloadAttachment
      ? {
          name: payloadAttachment.name,
          kind: payloadAttachment.kind,
          content: payloadAttachment.content,
        }
      : null,
  );
  focusInputWhenReady();
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

function stopStreaming(): void {
  chatStore.cancelStreaming();
  nextTick(() => {
    chatInputRef.value?.focus();
  });
}

onUnmounted(() => {
  window.removeEventListener(SHOWCASE_CHAT_DRAFT_EVENT, applyShowcaseDraft);
  if (copiedMessageIdTimeout) clearTimeout(copiedMessageIdTimeout);
  speechRecognition.value?.stop();
});
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 p-3 sm:p-4 border-b border-border/50 shrink-0">
      <div class="flex items-center gap-2 min-w-0 shrink-0">
        <button
          v-if="!chatStore.isSidebarOpen"
          class="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title="Open chat list"
          @click="chatStore.toggleSidebar"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
        <div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <Bot class="w-5 h-5 text-primary" />
        </div>
        <div class="min-w-0">
          <div
            v-if="isTitleLoading"
            class="mt-[8px] h-5 w-36 rounded-md bg-muted animate-pulse"
          />
          <h2
            v-else
            class="text-base sm:text-lg font-semibold truncate"
          >
            {{ conversationTitle || 'Chat' }}
          </h2>
          <div
            v-if="isTitleLoading"
            class="mt-1.5 h-3.5 w-48 rounded-md bg-muted/70 animate-pulse"
          />
          <p
            v-else
            class="text-xs sm:text-sm text-muted-foreground truncate"
          >
            Run workflows and ask questions
          </p>
        </div>
      </div>

      <div class="flex flex-col sm:flex-row gap-2 sm:gap-2 sm:flex-nowrap sm:items-end">
        <div class="grid grid-cols-2 gap-2 sm:flex sm:items-end sm:gap-2 flex-1 min-w-0">
          <div class="chat-select-wrap relative flex flex-col min-w-0 sm:max-w-[140px]">
            <select
              v-model="selectedCredentialId"
              class="chat-select min-h-[44px] sm:min-h-0 sm:h-9 rounded-lg border border-input bg-background pl-3 pr-9 py-2.5 sm:py-0 text-sm touch-manipulation w-full truncate appearance-none cursor-pointer"
              @change="onCredentialChange"
            >
              <option
                value=""
                disabled
              >
                Select...
              </option>
              <option
                v-for="cred in credentials"
                :key="cred.id"
                :value="cred.id"
              >
                {{ cred.name }}
              </option>
            </select>
            <ChevronDown class="chat-select-arrow pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground shrink-0" />
          </div>

          <div class="chat-select-wrap relative flex flex-col min-w-0 sm:max-w-[160px]">
            <select
              v-model="selectedModel"
              class="chat-select min-h-[44px] sm:min-h-0 sm:h-9 rounded-lg border border-input bg-background pl-3 pr-9 py-2.5 sm:py-0 text-sm disabled:opacity-50 touch-manipulation w-full truncate appearance-none cursor-pointer"
              :disabled="!selectedCredentialId || isLoadingModels || modelsLoadFailed"
            >
              <option
                value=""
                disabled
              >
                {{ isLoadingModels ? "Loading..." : modelsLoadFailed ? "Failed to load" : "Select..." }}
              </option>
              <option
                v-for="m in models"
                :key="m.id"
                :value="m.id"
              >
                {{ m.name }}
              </option>
            </select>
            <ChevronDown class="chat-select-arrow pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground shrink-0" />
          </div>
        </div>

        <p
          v-if="modelsLoadFailed"
          class="text-xs text-amber-600 dark:text-amber-400 sm:max-w-[220px]"
        >
          This credential's model list could not be loaded. Chat stays disabled until a model can be fetched.
        </p>
      </div>
    </div>

    <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
      <div
        v-if="isShowingConversation && messages.length === 0 && !chatStore.isStreaming"
        class="mx-auto flex flex-1 w-full flex-col items-center justify-center self-center text-center text-muted-foreground px-2 py-6 sm:py-8 gap-4"
      >
        <Send class="w-10 h-10 sm:w-12 sm:h-12 opacity-50" />
        <p class="text-xs sm:text-sm max-w-[280px] sm:max-w-none">
          Ask to run a workflow, list workflows, or ask about your data.
        </p>
      </div>
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
            'group/message relative rounded-2xl px-4 py-2.5 pr-10 text-sm leading-relaxed break-words',
            msg.workflowPreview ? 'w-[min(92%,920px)] max-w-[920px]' : 'max-w-[72%]',
            msg.role === 'user'
              ? 'bg-primary text-primary-foreground rounded-tr-sm'
              : 'bg-muted text-foreground rounded-tl-sm'
          ]"
        >
          <button
            type="button"
            class="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-lg text-current opacity-60 transition-opacity hover:bg-black/10 sm:opacity-0 sm:group-hover/message:opacity-70 hover:opacity-100"
            :title="copiedMessageId === msg.id ? 'Copied' : 'Copy'"
            :aria-label="copiedMessageId === msg.id ? 'Copied' : 'Copy message'"
            @click="copyMessage(msg)"
          >
            <Check
              v-if="copiedMessageId === msg.id"
              class="w-3.5 h-3.5"
            />
            <Copy
              v-else
              class="w-3.5 h-3.5"
            />
          </button>
          <!-- eslint-disable vue/no-v-html -->
          <div
            class="chat-markdown"
            @click="handleMarkdownImageClick"
            v-html="renderMarkdown(msg.content)"
          />
          <!-- eslint-enable vue/no-v-html -->
          <div
            v-if="msg.images && msg.images.length > 0"
            class="mt-2 flex flex-wrap gap-2"
          >
            <img
              v-for="(imgSrc, index) in msg.images"
              :key="`${msg.id}-${index}`"
              :src="imgSrc"
              alt="Generated image"
              class="max-h-48 max-w-full rounded-lg object-contain cursor-zoom-in border border-border/30 hover:border-border/60 transition-colors"
              @click.stop="imageLightboxSrc = imgSrc"
            >
          </div>
          <div
            v-if="msg.workflowPreview"
            class="mt-3 overflow-hidden rounded-xl border border-border/50 bg-background/70"
          >
            <div class="flex flex-col gap-2 border-b border-border/50 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">
                  {{ msg.workflowPreview.name }}
                </p>
                <p
                  v-if="msg.workflowPreview.description"
                  class="line-clamp-2 text-xs text-muted-foreground"
                >
                  {{ msg.workflowPreview.description }}
                </p>
              </div>
              <a
                :href="msg.workflowPreview.url"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-background px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
              >
                <ExternalLink class="h-3.5 w-3.5" />
                Open workflow
              </a>
            </div>
            <div class="h-64 min-h-0 w-full">
              <ReadonlyCanvasSurface
                :nodes="msg.workflowPreview.nodes"
                :edges="msg.workflowPreview.edges"
                :flow-key="msg.workflowPreview.id"
                empty-message="No workflow preview"
                :show-mini-map="false"
                :fit-padding="0.24"
                :max-zoom="1.1"
                :background-gap="28"
                :framed="false"
              />
            </div>
          </div>
          <div
            v-if="msg.attachmentName"
            class="mt-1.5 flex items-center gap-1 text-xs opacity-70"
          >
            <Paperclip class="w-3 h-3 shrink-0" />
            <span class="truncate">{{ msg.attachmentName }}</span>
          </div>
        </div>

        <div
          v-if="msg.role === 'user'"
          class="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5 text-xs font-semibold text-muted-foreground"
        >
          {{ userInitial }}
        </div>
      </div>

      <div
        v-if="chatStore.isStreaming"
        class="flex gap-3 justify-start"
      >
        <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
          <Bot class="w-4 h-4 text-primary" />
        </div>
        <div
          :class="[
            'rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed bg-muted text-foreground break-words',
            chatStore.streamingWorkflowPreview ? 'w-[min(92%,920px)] max-w-[920px]' : 'max-w-[72%]',
          ]"
        >
          <div
            v-if="chatStore.streamingSteps.length > 0"
            class="mb-3 space-y-1.5"
          >
            <div
              v-for="(step, index) in chatStore.streamingSteps"
              :key="`${step}-${index}`"
              class="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <Loader2
                v-if="index === chatStore.streamingSteps.length - 1 && !chatStore.streamingContent"
                class="w-3.5 h-3.5 shrink-0 animate-spin"
              />
              <span
                v-else
                class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-primary/20"
              >
                <span class="text-[10px] text-primary">✓</span>
              </span>
              <span>{{ step }}</span>
            </div>
          </div>
          <!-- eslint-disable vue/no-v-html -->
          <div
            v-if="chatStore.streamingContent"
            class="chat-markdown"
            @click="handleMarkdownImageClick"
            v-html="renderMarkdown(chatStore.streamingContent)"
          />
          <!-- eslint-enable vue/no-v-html -->
          <div
            v-if="!chatStore.streamingContent && chatStore.streamingImages.length === 0"
            class="flex items-center gap-2 text-muted-foreground"
          >
            <span>{{ chatStore.streamingSteps.length > 0 ? "Preparing response..." : "Heyming..." }}</span>
          </div>
          <div
            v-if="chatStore.streamingImages.length > 0"
            class="mt-2 flex flex-wrap gap-2"
          >
            <img
              v-for="(imgSrc, index) in chatStore.streamingImages"
              :key="`streaming-${index}`"
              :src="imgSrc"
              alt="Generated image"
              class="max-h-48 max-w-full rounded-lg object-contain cursor-zoom-in border border-border/30 hover:border-border/60 transition-colors"
              @click.stop="imageLightboxSrc = imgSrc"
            >
          </div>
          <div
            v-if="chatStore.streamingWorkflowPreview"
            class="mt-3 overflow-hidden rounded-xl border border-border/50 bg-background/70"
          >
            <div class="flex flex-col gap-2 border-b border-border/50 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">
                  {{ chatStore.streamingWorkflowPreview.name }}
                </p>
                <p
                  v-if="chatStore.streamingWorkflowPreview.description"
                  class="line-clamp-2 text-xs text-muted-foreground"
                >
                  {{ chatStore.streamingWorkflowPreview.description }}
                </p>
              </div>
              <a
                :href="chatStore.streamingWorkflowPreview.url"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-background px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
              >
                <ExternalLink class="h-3.5 w-3.5" />
                Open workflow
              </a>
            </div>
            <div class="h-64 min-h-0 w-full">
              <ReadonlyCanvasSurface
                :nodes="chatStore.streamingWorkflowPreview.nodes"
                :edges="chatStore.streamingWorkflowPreview.edges"
                :flow-key="chatStore.streamingWorkflowPreview.id"
                empty-message="No workflow preview"
                :show-mini-map="false"
                :fit-padding="0.24"
                :max-zoom="1.1"
                :background-gap="28"
                :framed="false"
              />
            </div>
          </div>
        </div>
      </div>

      <div ref="messagesEndRef" />
    </div>

    <ImageLightbox
      :src="imageLightboxSrc"
      alt="Generated image"
      @close="imageLightboxSrc = null"
    />

    <div class="chat-input-area shrink-0 px-3 sm:px-4 pt-3 sm:pt-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
      <input
        ref="fileInputRef"
        type="file"
        accept=".txt,.csv,.json,.md,.py,.ts,.js,.html,.xml,.yaml,.yml,.log,.jpg,.jpeg,.png,.gif,.webp,.pdf"
        class="hidden"
        @change="handleFileInputChange"
      >
      <div
        v-if="attachedFile || attachmentError"
        class="flex items-center gap-2 mb-2 px-1"
      >
        <div
          v-if="attachedFile"
          class="flex items-center gap-1.5 rounded-lg bg-muted/60 border border-border/40 px-2.5 py-1 text-xs text-foreground max-w-xs"
        >
          <Paperclip class="w-3 h-3 shrink-0 text-muted-foreground" />
          <span class="truncate">{{ attachedFile.name }}</span>
          <span class="text-muted-foreground shrink-0">· {{ attachedFile.sizeKb }} KB</span>
          <button
            type="button"
            class="shrink-0 ml-0.5 rounded hover:bg-muted/80 p-0.5"
            aria-label="Remove attachment"
            @click="clearAttachment"
          >
            <X class="w-3 h-3" />
          </button>
        </div>
        <p
          v-if="attachmentError"
          class="text-xs text-destructive"
        >
          {{ attachmentError }}
        </p>
      </div>
      <form
        class="flex items-center gap-2 rounded-2xl bg-muted/40 border border-border/40 px-3 py-2 min-h-[52px] focus-within:border-primary/30 focus-within:bg-muted/50 transition-colors"
        @submit.prevent="send"
      >
        <button
          type="button"
          class="shrink-0 h-9 w-9 min-h-[36px] min-w-[36px] rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/80 disabled:opacity-50 disabled:pointer-events-none touch-manipulation transition-colors"
          :disabled="chatStore.isStreaming || attachmentLoading"
          title="Attach file"
          aria-label="Attach file"
          @click="openFilePicker"
        >
          <Loader2
            v-if="attachmentLoading"
            class="w-4 h-4 animate-spin"
          />
          <Paperclip
            v-else
            class="w-4 h-4"
          />
        </button>
        <textarea
          ref="chatInputRef"
          v-model="input"
          rows="1"
          placeholder="Type a message..."
          class="chat-input flex-1 min-h-[44px] max-h-40 resize-none bg-transparent border-0 px-1 py-3 text-sm text-left focus:outline-none focus:ring-0 disabled:opacity-50 touch-manipulation placeholder:text-muted-foreground leading-5"
          :disabled="chatStore.isStreaming || !canSendMessage || !selectedCredentialId || !selectedModel || modelsLoadFailed"
          @keydown="onKeydown"
          @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = ($event.target as HTMLTextAreaElement).scrollHeight + 'px'"
        />
        <button
          v-if="isSpeechSupported"
          type="button"
          class="shrink-0 h-9 w-9 min-h-[36px] min-w-[36px] rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/80 disabled:opacity-50 disabled:pointer-events-none touch-manipulation transition-colors"
          :disabled="chatStore.isStreaming || !canSendMessage || isFixingTranscription || !selectedCredentialId || !selectedModel || modelsLoadFailed"
          :title="isListening ? 'Stop voice input' : isFixingTranscription ? 'Fixing...' : 'Voice input'"
          @click="toggleSpeechInput"
        >
          <Loader2
            v-if="isFixingTranscription"
            class="w-4 h-4 animate-spin"
          />
          <component
            :is="isListening ? MicOff : Mic"
            v-else
            class="w-4 h-4"
          />
        </button>
        <Button
          v-if="!chatStore.isStreaming"
          type="submit"
          variant="gradient"
          size="icon"
          :disabled="!input.trim() || !canSendMessage || !selectedCredentialId || !selectedModel || modelsLoadFailed || !!attachmentError || attachmentLoading"
          class="shrink-0 h-9 w-9 min-h-[36px] min-w-[36px] rounded-xl touch-manipulation"
        >
          <Send class="w-4 h-4" />
        </Button>
        <Button
          v-else
          type="button"
          variant="destructive"
          size="icon"
          class="shrink-0 h-9 w-9 min-h-[36px] min-w-[36px] rounded-xl touch-manipulation"
          @click="stopStreaming"
        >
          <Square class="w-4 h-4" />
        </Button>
      </form>
      <p
        v-if="credentialError"
        class="mt-2 text-xs text-destructive"
      >
        {{ credentialError }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.chat-markdown :deep(p) {
  margin: 0.45em 0;
}

.chat-markdown :deep(p:first-child) {
  margin-top: 0;
}

.chat-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.chat-markdown :deep(ul),
.chat-markdown :deep(ol) {
  margin: 0.45em 0;
  padding-left: 1.25rem;
}

.chat-markdown :deep(blockquote) {
  border-left: 2px solid hsl(var(--border));
  margin: 0.6em 0;
  padding-left: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.chat-markdown :deep(code) {
  background: hsl(var(--background) / 0.65);
  border-radius: 0.25rem;
  font-size: 0.875em;
  padding: 0.125em 0.35em;
}

.chat-markdown :deep(pre) {
  background: hsl(var(--background) / 0.75);
  border-radius: 0.5rem;
  margin: 0.65em 0;
  overflow-x: auto;
  padding: 0.75rem;
}

.chat-markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.chat-markdown :deep(a) {
  color: inherit;
  text-decoration: underline;
}

.chat-markdown :deep(img),
.chat-markdown :deep(video) {
  border: 1px solid hsl(var(--border) / 0.35);
  border-radius: 0.5rem;
  cursor: zoom-in;
  margin: 0.65rem 0;
  max-height: 12rem;
  max-width: 100%;
  object-fit: contain;
}
</style>
