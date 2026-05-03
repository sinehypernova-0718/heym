<script setup lang="ts">
import { computed } from "vue";
import { Bot } from "lucide-vue-next";
import { useWorkflowStore } from "@/stores/workflow";
import Button from "@/components/ui/Button.vue";

interface Props {
  nodeId: string;
  fieldKey: string;
}

const props = defineProps<Props>();
const workflowStore = useWorkflowStore();

const isAgentProvided = computed((): boolean => {
  const node = workflowStore.nodes.find((n) => n.id === props.nodeId);
  const fields: string[] = node?.data.agentProvidedFields ?? [];
  return fields.includes(props.fieldKey);
});

function toggle(): void {
  const node = workflowStore.nodes.find((n) => n.id === props.nodeId);
  if (!node) return;
  const current: string[] = node.data.agentProvidedFields ?? [];
  const updated = isAgentProvided.value
    ? current.filter((f) => f !== props.fieldKey)
    : [...current, props.fieldKey];
  workflowStore.updateNode(props.nodeId, { agentProvidedFields: updated });
}
</script>

<template>
  <Button
    variant="ghost"
    size="icon"
    class="h-6 w-6 shrink-0"
    :class="
      isAgentProvided
        ? 'text-violet-500 hover:text-violet-400'
        : 'text-muted-foreground hover:text-foreground'
    "
    :title="
      isAgentProvided
        ? 'Agent fills this — click to use fixed value'
        : 'Click to let agent fill this at runtime'
    "
    type="button"
    @click="toggle"
  >
    <Bot class="h-3.5 w-3.5" />
  </Button>
</template>
