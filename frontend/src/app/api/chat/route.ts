// Chat endpoint — proxies to the real orchestration backend (Sprint 4).
//
// useChat POSTs the message history here. We start a real task on FastAPI
// (POST /api/tasks), which runs the LangGraph planner and pauses at the
// approval interrupt, then stream back assistant text plus the real plan as a
// typed `data-plan` part (carrying the backend task id so approval can resume
// the exact graph). No mock plan anymore.

import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import { BACKEND_URL, DEFAULT_SITE_SLUG } from "@/lib/backend";
import type { ChatUIMessage, Plan, PlanStep, WpChannel } from "@/lib/types";

export const maxDuration = 60;

type BackendStep = {
  id: string;
  tool: string;
  title: string;
  channel: WpChannel;
  preview?: { preview?: unknown } | null;
};

function lastUserText(messages: ChatUIMessage[]): string {
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUser) return "";
  return lastUser.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join(" ")
    .trim();
}

function toStep(s: BackendStep): PlanStep {
  return {
    id: s.id,
    title: s.title,
    description: `${s.channel} · ${s.tool}`,
    tool: s.tool,
    channel: s.channel,
    diff: s.preview?.preview
      ? JSON.stringify(s.preview.preview, null, 2)
      : undefined,
  };
}

export async function POST(req: Request) {
  const body = (await req.json()) as {
    messages: ChatUIMessage[];
    siteSlug?: string;
  };
  const instruction = lastUserText(body.messages ?? []);
  const siteSlug = body.siteSlug ?? DEFAULT_SITE_SLUG;

  let ok = false;
  let plan: Plan | null = null;
  let errorDetail = "";

  try {
    const res = await fetch(`${BACKEND_URL}/api/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction, site_slug: siteSlug }),
    });
    const data = await res.json();
    if (res.ok) {
      ok = true;
      plan = {
        taskId: data.task_id,
        summary: data.summary,
        steps: (data.plan ?? []).map(toStep),
      };
    } else {
      errorDetail = data.detail ?? `Backend error (${res.status})`;
    }
  } catch (err) {
    errorDetail = err instanceof Error ? err.message : "Backend unreachable";
  }

  const stream = createUIMessageStream<ChatUIMessage>({
    execute: async ({ writer }) => {
      const id = "assistant-intro";
      writer.write({ type: "text-start", id });
      const intro = ok
        ? `I've planned ${plan!.steps.length} step(s). Review and approve them below — nothing is written to your site until you do.`
        : `I couldn't plan that: ${errorDetail}`;
      for (const word of intro.split(" ")) {
        writer.write({ type: "text-delta", id, delta: word + " " });
      }
      writer.write({ type: "text-end", id });
      if (ok && plan) {
        writer.write({ type: "data-plan", data: plan });
      }
    },
  });

  return createUIMessageStreamResponse({ stream });
}
