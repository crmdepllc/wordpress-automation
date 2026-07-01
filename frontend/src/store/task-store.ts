// Zustand store for the live task state: the current plan, where it is in its
// lifecycle, and the streaming tool-call log. The chat panel feeds plans in
// (from the real backend); the approval modal drives approve/reject, which
// resumes the LangGraph task and streams execution back.

import { create } from "zustand";

import type { Plan, TaskStatus, ToolLogEntry } from "@/lib/types";

type TaskState = {
  status: TaskStatus;
  plan: Plan | null;
  log: ToolLogEntry[];

  /** A plan arrived from the chat stream — pause for approval. */
  proposePlan: (plan: Plan) => void;
  setStatus: (status: TaskStatus) => void;
  addLog: (entry: ToolLogEntry) => void;
  reset: () => void;
};

export const useTaskStore = create<TaskState>((set) => ({
  status: "idle",
  plan: null,
  log: [],

  proposePlan: (plan) => set({ plan, status: "awaiting_approval", log: [] }),
  setStatus: (status) => set({ status }),
  addLog: (entry) => set((s) => ({ log: [...s.log, entry] })),
  reset: () => set({ status: "idle", plan: null, log: [] }),
}));

// Backend execution events (ndjson) as emitted by the orchestrator graph.
type ToolEvent = {
  type: "tool";
  id: string;
  step_id: string;
  tool: string;
  channel: ToolLogEntry["channel"];
  status: ToolLogEntry["status"];
  message: string;
};
type ReportEvent = { type: "report"; status: TaskStatus; report: unknown };
type ResumeEvent = ToolEvent | ReportEvent;

/**
 * Resume the active task with a decision. Approve → the graph executes and
 * streams a tool event per step, then a final report. Reject → the graph
 * reports without writing. Either way, the real backend drives the outcome.
 */
export async function resumeTask(decision: "approve" | "reject") {
  const { plan, setStatus, addLog } = useTaskStore.getState();
  const taskId = plan?.taskId;
  if (!taskId) return;

  setStatus(decision === "approve" ? "executing" : "rejected");

  const res = await fetch(`/api/tasks/${taskId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!res.body) {
    setStatus("completed");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handle = (event: ResumeEvent) => {
    if (event.type === "tool") {
      addLog({
        id: event.id,
        stepId: event.step_id,
        tool: event.tool,
        channel: event.channel,
        status: event.status,
        message: event.message,
        at: Date.now(),
      });
    } else if (event.type === "report") {
      setStatus(event.status);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) handle(JSON.parse(line) as ResumeEvent);
    }
  }
}
