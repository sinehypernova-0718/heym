import { ref } from "vue";

import { useChatStore } from "@/stores/chat";

export function useQuickPrompts(): {
  editingIndex: ReturnType<typeof ref<number | null>>;
  editingValue: ReturnType<typeof ref<string>>;
  startEdit: (index: number) => void;
  cancelEdit: () => void;
  commitEdit: () => Promise<void>;
  onEditKeydown: (event: KeyboardEvent) => void;
} {
  const chatStore = useChatStore();
  const editingIndex = ref<number | null>(null);
  const editingValue = ref("");

  function startEdit(index: number): void {
    editingIndex.value = index;
    editingValue.value = chatStore.quickPrompts[index] ?? "";
  }

  function cancelEdit(): void {
    editingIndex.value = null;
    editingValue.value = "";
  }

  async function commitEdit(): Promise<void> {
    const index = editingIndex.value;
    if (index === null) return;
    const trimmed = editingValue.value.trim();
    if (!trimmed) {
      cancelEdit();
      return;
    }
    const updated = [...chatStore.quickPrompts];
    updated[index] = trimmed;
    cancelEdit();
    await chatStore.saveQuickPrompts(updated);
  }

  function onEditKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
      event.preventDefault();
      void commitEdit();
    }
    if (event.key === "Escape") {
      cancelEdit();
    }
  }

  return { editingIndex, editingValue, startEdit, cancelEdit, commitEdit, onEditKeydown };
}
