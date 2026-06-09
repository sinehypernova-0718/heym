import { reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { useWorkflowStore } from "@/stores/workflow";
import { workflowApi } from "@/services/api";
import {
  RUNBOOK_INPUT_TEXT,
  RUNBOOK_QUERY_FLAG,
  RUNBOOK_QUERY_VALUE,
  RUNBOOK_RUN_DELAY_MS,
  RUNBOOK_STEPS,
  RUNBOOK_WORKFLOW_NAME,
  buildRunbookEdge,
  buildRunbookNode,
  buildRunbookStickyNode,
} from "@/features/runbook/runbookScript";
import type { WorkflowNode } from "@/types/workflow";

// Module-level singleton state: shared by every caller without a Pinia store.
const isRunbookPlaying = ref(false);

interface CursorPoint {
  x: number;
  y: number;
}

/** Simulated cursor position consumed by RunbookCursor.vue (CSS-transitioned). */
export const runbookCursor = reactive<{ visible: boolean; x: number; y: number }>({
  visible: false,
  x: 0,
  y: 0,
});

function moveCursorTo(point: CursorPoint): void {
  runbookCursor.x = point.x;
  runbookCursor.y = point.y;
}

/** Center of the first element matching `selector`, or `fallback` if absent. */
function elementCenter(selector: string, fallback: CursorPoint): CursorPoint {
  const el = document.querySelector(selector);
  if (!el) return fallback;
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function useRunbookPlayer(): {
  isRunbookPlaying: typeof isRunbookPlaying;
  startRunbookNewWorkflow: () => Promise<void>;
  playRunbookInPlace: () => Promise<void>;
} {
  const router = useRouter();
  const workflowStore = useWorkflowStore();

  /** Create a fresh demo workflow and navigate to it with the auto-play flag. */
  async function startRunbookNewWorkflow(): Promise<void> {
    if (isRunbookPlaying.value) return;
    const workflow = await workflowApi.create({
      name: RUNBOOK_WORKFLOW_NAME,
      description: "Auto-generated Heym runbook demo.",
    });
    await router.push({
      name: "editor",
      params: { id: workflow.id },
      query: { [RUNBOOK_QUERY_FLAG]: RUNBOOK_QUERY_VALUE },
    });
    // EditorView consumes the query flag on mount and calls playRunbookInPlace().
  }

  /**
   * Choreographed demo: the node panel filters first (cursor at the left),
   * then the nodes are placed (cursor at the center), then it runs (cursor at
   * the run control). The simulated cursor glides between each phase.
   */
  async function playRunbookInPlace(): Promise<void> {
    if (isRunbookPlaying.value) return;
    if (!workflowStore.currentWorkflow) return;
    isRunbookPlaying.value = true; // node panel filters + pulses immediately
    const reduced = prefersReducedMotion();
    // Hide the real cursor; the simulated cursor guides the demo instead.
    document.body.classList.add("runbook-playing");

    try {
      if (!reduced) {
        // Phase 1: cursor appears center, then glides up to the 3 filtered nodes
        // in the top-left node panel.
        runbookCursor.x = window.innerWidth / 2;
        runbookCursor.y = window.innerHeight / 2;
        runbookCursor.visible = true;
        await sleep(50);
        moveCursorTo(
          elementCenter('[data-node-index="0"]', { x: 150, y: 170 }),
        );
        await sleep(1600);

        // Phase 2: cursor moves to the canvas center before the nodes appear.
        moveCursorTo({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
        await sleep(750);
      }

      // Intro sticky note appears first and narrates the demo.
      if (!reduced) await sleep(200);
      workflowStore.addNode(buildRunbookStickyNode());

      const created: WorkflowNode[] = [];
      for (let i = 0; i < RUNBOOK_STEPS.length; i++) {
        if (!reduced) await sleep(RUNBOOK_STEPS[i].enterDelayMs);
        workflowStore.addNode(buildRunbookNode(i));
        // addNode may rewrite data.label to keep it unique; re-read the stored node.
        const stored = workflowStore.nodes[workflowStore.nodes.length - 1];
        created.push(stored);
        if (i > 0) {
          workflowStore.addEdge(buildRunbookEdge(created[i - 1].id, stored.id));
        }
        // Clear the transient entrance flag after the slide-in finishes.
        if (reduced) {
          workflowStore.updateNode(stored.id, { __runbookEntrance: undefined });
        } else {
          window.setTimeout(() => {
            workflowStore.updateNode(stored.id, { __runbookEntrance: undefined });
          }, 1050);
        }
      }

      // Phase 3: cursor glides to the run control, then the workflow runs.
      if (!reduced) {
        moveCursorTo(
          elementCenter("[data-runbook-run]", { x: window.innerWidth - 150, y: 120 }),
        );
      }
      await sleep(reduced ? 0 : RUNBOOK_RUN_DELAY_MS);

      // Feed the sample input and run the real executor.
      workflowStore.runInputValues.text = RUNBOOK_INPUT_TEXT;
      await workflowStore.executeWorkflow(workflowStore.buildExecutionRequestBody());
    } finally {
      isRunbookPlaying.value = false;
      runbookCursor.visible = false;
      document.body.classList.remove("runbook-playing");
    }
  }

  return { isRunbookPlaying, startRunbookNewWorkflow, playRunbookInPlace };
}
