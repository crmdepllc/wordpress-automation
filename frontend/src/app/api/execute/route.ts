// Mocked execution endpoint for Sprint 2.
//
// Called after the user approves a plan. Streams newline-delimited JSON
// ToolLogEntry events — one "running" then one "success" per step — so the
// task log can render execution live. Later sprints replace this with the
// real LangGraph execute phase emitting actual tool-call results.

import type { Plan, ToolLogEntry } from "@/lib/types";

export const maxDuration = 60;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function POST(req: Request) {
  const { plan } = (await req.json()) as { plan: Plan };
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (entry: ToolLogEntry) =>
        controller.enqueue(encoder.encode(JSON.stringify(entry) + "\n"));

      let seq = 0;
      for (const step of plan.steps) {
        send({
          id: `log-${seq++}`,
          stepId: step.id,
          tool: step.tool,
          channel: step.channel,
          status: "running",
          message: `${step.title}…`,
          at: Date.now(),
        });
        await sleep(700);
        send({
          id: `log-${seq++}`,
          stepId: step.id,
          tool: step.tool,
          channel: step.channel,
          status: "success",
          message: `${step.title} — done`,
          at: Date.now(),
        });
        await sleep(200);
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}
