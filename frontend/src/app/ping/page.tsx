"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function PingPage() {
  const [prompt, setPrompt] = useState(
    "Say hello and confirm the agent loop is working."
  );
  const [response, setResponse] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendPing() {
    setLoading(true);
    setError("");
    setResponse("");
    try {
      const res = await fetch(`${API_BASE}/api/ping`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? `Request failed (${res.status})`);
      }
      setResponse(data.response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center bg-background p-6">
      <div className="w-full max-w-2xl space-y-6 rounded-xl border border-border bg-card p-8 shadow-sm">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-card-foreground">
            Agent ping spike
          </h1>
          <p className="text-sm text-muted-foreground">
            Sprint 1 spike — send a prompt end-to-end through the FastAPI backend
            to the LangGraph ping node.{" "}
            <Link href="/" className="text-foreground underline underline-offset-4">
              Back to dashboard
            </Link>
          </p>
        </header>

        <div className="space-y-3">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-lg border border-border bg-background p-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            placeholder="Ask the agent something…"
          />
          <Button
            size="lg"
            onClick={sendPing}
            disabled={loading || prompt.trim().length === 0}
          >
            {loading ? "Pinging…" : "Send ping"}
          </Button>
        </div>

        {error && (
          <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {response && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Agent response
            </p>
            <div className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm text-foreground">
              {response}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
