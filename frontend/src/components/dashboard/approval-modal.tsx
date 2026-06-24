"use client";

import { Check, ShieldAlert, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { runExecution, useTaskStore } from "@/store/task-store";

// The human approval gate. No write happens until the user clicks Approve —
// this mock mirrors the real LangGraph interrupt that Sprint 4 wires in.
export function ApprovalModal() {
  const status = useTaskStore((s) => s.status);
  const plan = useTaskStore((s) => s.plan);
  const reject = useTaskStore((s) => s.reject);

  const open = status === "awaiting_approval" && plan !== null;

  return (
    <Dialog open={open}>
      <DialogContent className="max-w-2xl">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
            <ShieldAlert className="size-4" />
          </span>
          <div className="space-y-1">
            <DialogTitle>Review &amp; approve plan</DialogTitle>
            <DialogDescription>{plan?.summary}</DialogDescription>
          </div>
        </div>

        <div className="max-h-[50vh] space-y-3 overflow-y-auto pr-1">
          {plan?.steps.map((step, i) => (
            <div
              key={step.id}
              className="rounded-lg border border-border bg-background p-3"
            >
              <div className="flex items-center gap-2">
                <Badge variant="muted">{i + 1}</Badge>
                <span className="flex-1 text-sm font-medium text-foreground">
                  {step.title}
                </span>
                <Badge variant="outline">{step.channel}</Badge>
              </div>
              <p className="mt-1.5 text-sm text-muted-foreground">
                {step.description}
              </p>
              {step.diff && (
                <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-2.5 font-mono text-xs text-foreground">
                  {step.diff}
                </pre>
              )}
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={reject}>
            <X className="size-4" />
            Reject
          </Button>
          <Button
            onClick={() => {
              if (plan) void runExecution(plan);
            }}
          >
            <Check className="size-4" />
            Approve &amp; run
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
