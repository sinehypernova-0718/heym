<script setup lang="ts">
import { ref } from "vue";
import { Check, Copy } from "lucide-vue-next";

const props = defineProps<{
  text: string;
}>();

const copied = ref(false);

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.text);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    // Silently ignore clipboard failures.
  }
}
</script>

<template>
  <button
    type="button"
    class="inline-flex h-6 w-6 items-center justify-center rounded-md border border-border/60 bg-background/80 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:bg-accent hover:text-accent-foreground"
    :title="copied ? 'Copied' : 'Copy'"
    @click.stop="copy"
  >
    <Check
      v-if="copied"
      class="h-3 w-3 text-emerald-500"
    />
    <Copy
      v-else
      class="h-3 w-3"
    />
  </button>
</template>
