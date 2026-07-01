// Resume proxy — approve/reject a paused task and stream execution back.
//
// Forwards the decision to FastAPI (POST /api/tasks/{id}/resume) and pipes the
// ndjson stream of tool events + final report straight through to the browser.

import { BACKEND_URL } from "@/lib/backend";

export const maxDuration = 120;

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const body = (await req.json()) as { decision: "approve" | "reject" };

  const res = await fetch(`${BACKEND_URL}/api/tasks/${id}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision: body.decision }),
  });

  if (!res.ok || !res.body) {
    const detail = await res.text();
    return new Response(detail || "Resume failed", { status: res.status || 502 });
  }

  return new Response(res.body, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}
