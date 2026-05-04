<script setup lang="ts">
import { ref, watch } from "vue";
import { Loader2, Sparkles, X } from "lucide-vue-next";

import type { ExpressionEvaluateResponse } from "@/types/workflow";
import type { CredentialListItem, LLMModel } from "@/types/credential";
import { credentialsApi, expressionApi } from "@/services/api";

interface CanvasNodeResult {
  node_id: string;
  label: string;
  output: unknown;
}

interface Props {
  open: boolean;
  workflowId: string;
  currentNodeId: string | null;
  canvasNodeResults: CanvasNodeResult[];
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "apply", expression: string): void;
}>();

const description = ref("");
const credentialId = ref("");
const modelName = ref("");
const credentials = ref<CredentialListItem[]>([]);
const models = ref<LLMModel[]>([]);
const generatedExpression = ref<string | null>(null);
const evaluateResult = ref<ExpressionEvaluateResponse | null>(null);
const evaluateError = ref<string | null>(null);
const generating = ref(false);
const evaluating = ref(false);
const error = ref<string | null>(null);
const loadingCredentials = ref(false);

const canGenerate = (): boolean =>
  description.value.trim().length > 0 && credentialId.value !== "" && modelName.value !== "";

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      return;
    }
    generatedExpression.value = null;
    evaluateResult.value = null;
    evaluateError.value = null;
    error.value = null;
    if (credentials.value.length === 0) {
      loadingCredentials.value = true;
      try {
        credentials.value = await credentialsApi.listLLM();
      } finally {
        loadingCredentials.value = false;
      }
    }
  },
);

async function onCredentialChange(): Promise<void> {
  modelName.value = "";
  models.value = [];
  if (!credentialId.value) {
    return;
  }
  models.value = await credentialsApi.getModels(credentialId.value);
  if (models.value.length > 0) {
    modelName.value = models.value[0].id;
  }
}

async function generate(): Promise<void> {
  if (!canGenerate() || generating.value) {
    return;
  }
  generating.value = true;
  error.value = null;
  evaluateResult.value = null;
  evaluateError.value = null;
  try {
    const res = await expressionApi.generate({
      description: description.value.trim(),
      workflow_id: props.workflowId,
      credential_id: credentialId.value,
      model: modelName.value,
      current_node_id: props.currentNodeId,
      node_results: props.canvasNodeResults,
    });
    generatedExpression.value = res.expression;
    await evaluateGenerated(res.expression);
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    generating.value = false;
  }
}

async function evaluateGenerated(expression: string): Promise<void> {
  evaluating.value = true;
  evaluateError.value = null;
  try {
    evaluateResult.value = await expressionApi.evaluate({
      expression,
      workflow_id: props.workflowId,
      current_node_id: props.currentNodeId ?? "",
      node_results: props.canvasNodeResults,
    });
  } catch (e: unknown) {
    evaluateError.value = e instanceof Error ? e.message : String(e);
  } finally {
    evaluating.value = false;
  }
}

function apply(): void {
  if (!generatedExpression.value) {
    return;
  }
  emit("apply", generatedExpression.value);
  emit("update:open", false);
}

function close(): void {
  emit("update:open", false);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="pointer-events-none fixed inset-0 z-[10001] flex items-center justify-center"
    >
      <div
        class="pointer-events-auto fixed inset-0 bg-black/60 backdrop-blur-sm"
        @click="close"
      />

      <div
        class="pointer-events-auto relative z-10 mx-4 flex w-[min(96vw,500px)] flex-col overflow-hidden rounded-lg border border-indigo-500/60 bg-background shadow-2xl"
        @click.stop
      >
        <div class="flex shrink-0 items-center gap-2 border-b border-indigo-900/60 bg-gradient-to-r from-indigo-950 to-indigo-900/80 px-4 py-3">
          <Sparkles class="h-4 w-4 shrink-0 text-indigo-400" />
          <h3 class="flex-1 text-sm font-semibold text-indigo-200">
            Build with AI
          </h3>
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-md text-indigo-400 transition-colors hover:bg-indigo-800/60 hover:text-indigo-200"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="flex flex-col gap-3 p-4">
          <div>
            <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Describe what you want
            </div>
            <textarea
              v-model="description"
              rows="3"
              placeholder="e.g. Get the customer name from the API response"
              class="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:border-primary focus-visible:outline-none"
            />
          </div>

          <div class="flex gap-3">
            <div class="flex flex-1 flex-col gap-1">
              <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Credential
              </div>
              <select
                v-model="credentialId"
                class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none"
                @change="onCredentialChange"
              >
                <option value="">
                  Select…
                </option>
                <option
                  v-for="c in credentials"
                  :key="c.id"
                  :value="c.id"
                >
                  {{ c.name }}
                </option>
              </select>
              <div
                v-if="loadingCredentials"
                class="flex items-center gap-2 text-xs text-muted-foreground"
              >
                <Loader2 class="h-3.5 w-3.5 animate-spin" />
                <span>Loading credentials…</span>
              </div>
            </div>
            <div class="flex flex-1 flex-col gap-1">
              <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Model
              </div>
              <select
                v-model="modelName"
                :disabled="models.length === 0"
                class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">
                  Select…
                </option>
                <option
                  v-for="m in models"
                  :key="m.id"
                  :value="m.id"
                >
                  {{ m.name }}
                </option>
              </select>
            </div>
          </div>

          <p
            v-if="!loadingCredentials && credentials.length === 0"
            class="text-xs text-muted-foreground"
          >
            No credentials configured – add one in Settings.
          </p>

          <div
            v-if="error"
            class="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive"
          >
            {{ error }}
          </div>

          <div
            v-if="generating && !generatedExpression"
            class="flex items-center gap-2 text-sm text-indigo-400"
          >
            <Loader2 class="h-4 w-4 animate-spin" />
            <span>Generating…</span>
          </div>

          <template v-if="generatedExpression">
            <div class="space-y-1">
              <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Generated expression
              </div>
              <div class="rounded-md border bg-muted/30 px-3 py-2 font-mono text-sm text-cyan-400 break-all">
                {{ generatedExpression }}
              </div>
            </div>

            <div class="space-y-1">
              <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Evaluated output
              </div>
              <div
                v-if="evaluating"
                class="flex items-center gap-2 text-xs text-muted-foreground"
              >
                <Loader2 class="h-3.5 w-3.5 animate-spin" />
                <span>Evaluating…</span>
              </div>
              <div
                v-else-if="evaluateError"
                class="text-xs italic text-muted-foreground"
              >
                {{ evaluateError }}
              </div>
              <div
                v-else-if="evaluateResult && !evaluateResult.error"
                class="rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs break-all"
              >
                {{ JSON.stringify(evaluateResult.result) }}
              </div>
              <div
                v-else-if="evaluateResult?.error"
                class="text-xs italic text-muted-foreground"
              >
                {{ evaluateResult.error }}
              </div>
              <div
                v-else
                class="text-xs italic text-muted-foreground"
              >
                No result – run the workflow first.
              </div>
            </div>
          </template>
        </div>

        <div class="flex shrink-0 items-center justify-end gap-2 border-t px-4 py-3">
          <button
            type="button"
            class="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent"
            @click="close"
          >
            Cancel
          </button>
          <button
            type="button"
            :disabled="!canGenerate() || generating"
            class="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            @click="generate"
          >
            <Loader2
              v-if="generating"
              class="h-3.5 w-3.5 animate-spin"
            />
            {{ generatedExpression ? "Regenerate" : "Generate" }}
          </button>
          <button
            v-if="generatedExpression"
            type="button"
            class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
            @click="apply"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
