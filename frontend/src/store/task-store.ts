// Zustand store for the live task state: the current plan, where it is in its
// lifecycle, and the streaming tool-call log. The chat panel feeds plans in;
// the approval modal drives the status; the task log panel renders the log.

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
  reject: () => void;
  reset: () => void;
};

export const useTaskStore = create<TaskState>((set) => ({
  status: "idle",
  plan: null,
  log: [],

  proposePlan: (plan) => set({ plan, status: "awaiting_approval", log: [] }),
  setStatus: (status) => set({ status }),
  addLog: (entry) => set((s) => ({ log: [...s.log, entry] })),
  reject: () => set({ status: "rejected" }),
  reset: () => set({ status: "idle", plan: null, log: [] }),
}));

/**
 * Approve the active plan and stream its execution from the mocked /api/execute
 * endpoint into the store. Resolves when the stream completes.
 */
export async function runExecution(plan: Plan) {
  const { setStatus, addLog } = useTaskStore.getState();
  setStatus("executing");

  const res = await fetch("/api/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  if (!res.body) {
    setStatus("completed");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) addLog(JSON.parse(line) as ToolLogEntry);
    }
  }

  setStatus("completed");
}
