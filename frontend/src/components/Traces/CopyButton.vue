<script setup lang="ts">
import { ref } from "vue";
import { Check, Copy } from "lucide-vue-next";

import Button from "@/components/ui/Button.vue";

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
  <Button
    variant="ghost"
    size="sm"
    class="h-6 w-6 shrink-0 p-0"
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
  </Button>
</template>
