// Mocked chat endpoint for Sprint 2.
//
// useChat (Vercel AI SDK) POSTs the message history here. We stream back an
// assistant text response, then emit a typed `data-plan` part describing the
// changes the agent intends to make. In later sprints this is replaced by the
// real LangGraph orchestrator's planning output — the wire format is the same,
// so the frontend won't need to change.

import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import { buildMockPlan } from "@/lib/mock-data";
import type { ChatUIMessage } from "@/lib/types";

export const maxDuration = 30;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function lastUserText(messages: ChatUIMessage[]): string {
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUser) return "build a site";
  return lastUser.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join(" ")
    .trim();
}

export async function POST(req: Request) {
  const body = (await req.json()) as { messages: ChatUIMessage[] };
  const request = lastUserText(body.messages ?? []);
  const plan = buildMockPlan(request);

  const stream = createUIMessageStream<ChatUIMessage>({
    execute: async ({ writer }) => {
      const id = "assistant-intro";
      writer.write({ type: "text-start", id });

      const intro =
        `Here's how I'd approach that. I've drafted a ${plan.steps.length}-step plan ` +
        `covering theme, pages, and the Elementor CSS rebuild. ` +
        `Nothing is written to your site until you approve it below.`;

      for (const word of intro.split(" ")) {
        writer.write({ type: "text-delta", id, delta: word + " " });
        await sleep(25);
      }
      writer.write({ type: "text-end", id });

      // Emit the structured plan as a typed data part.
      writer.write({ type: "data-plan", data: plan });
    },
    onError: (error) =>
      error instanceof Error ? error.message : "Unknown stream error",
  });

  return createUIMessageStreamResponse({ stream });
}
