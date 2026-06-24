"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { TaskStatus } from "@/lib/types";
import { useTaskStore } from "@/store/task-store";

const STATUS_LABEL: Record<TaskStatus, string> = {
  idle: "Idle",
  planning: "Planning",
  awaiting_approval: "Awaiting approval",
  executing: "Executing",
  completed: "Completed",
  rejected: "Rejected",
};

function statusVariant(status: TaskStatus) {
  if (status === "completed") return "success" as const;
  if (status === "rejected") return "destructive" as const;
  if (status === "idle") return "muted" as const;
  return "secondary" as const;
}

export function TaskLogPanel() {
  const status = useTaskStore((s) => s.status);
  const log = useTaskStore((s) => s.log);

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between px-4 py-4">
        <h2 className="text-sm font-semibold tracking-tight">Task log</h2>
        <Badge variant={statusVariant(status)}>{STATUS_LABEL[status]}</Badge>
      </div>

      <Separator />

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {log.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {status === "executing"
              ? "Starting…"
              : "Tool calls appear here once a plan is approved and runs."}
          </p>
        ) : (
          <ol className="space-y-3">
            {log.map((entry) => (
              <li key={entry.id} className="flex gap-2.5">
                <span className="mt-0.5">
                  {entry.status === "running" && (
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                  )}
                  {entry.status === "success" && (
                    <CheckCircle2 className="size-4 text-foreground" />
                  )}
                  {entry.status === "error" && (
                    <XCircle className="size-4 text-destructive" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-tight text-foreground">
                    {entry.message}
                  </p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Badge variant="outline">{entry.channel}</Badge>
                    <span className="truncate font-mono text-xs text-muted-foreground">
                      {entry.tool}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      {status === "completed" && (
        <>
          <Separator />
          <div className="flex items-center gap-2 px-4 py-3 text-sm text-foreground">
            <Circle className="size-2 fill-current" />
            All steps applied. CSS regenerated.
          </div>
        </>
      )}
    </aside>
  );
}
