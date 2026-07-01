"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { DEFAULT_SITE_SLUG } from "@/lib/backend";
import type { ChatUIMessage } from "@/lib/types";
import { useTaskStore } from "@/store/task-store";

const SUGGESTIONS = [
  "Build a 3-page portfolio site for a photographer, dark minimal theme",
  "Add a contact page with a form and set up SEO",
];

function messageText(message: ChatUIMessage): string {
  return message.parts
    .filter((p) => p.type === "text")
    .map((p) => (p.type === "text" ? p.text : ""))
    .join("");
}

export function ChatPanel() {
  const { messages, sendMessage, status } = useChat<ChatUIMessage>({
    transport: new DefaultChatTransport({
      api: "/api/chat",
      body: { siteSlug: DEFAULT_SITE_SLUG },
    }),
  });
  const [input, setInput] = useState("");
  const proposePlan = useTaskStore((s) => s.proposePlan);
  const setStatus = useTaskStore((s) => s.setStatus);

  // Surface any plan the stream emits to the approval flow — once per message.
  const proposedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    for (const m of messages) {
      if (m.role !== "assistant") continue;
      const planPart = m.parts.find((p) => p.type === "data-plan");
      if (planPart?.type === "data-plan" && !proposedRef.current.has(m.id)) {
        proposedRef.current.add(m.id);
        proposePlan(planPart.data);
      }
    }
  }, [messages, proposePlan]);

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const busy = status === "submitted" || status === "streaming";

  function submit(text: string) {
    const value = text.trim();
    if (!value || busy) return;
    setStatus("planning");
    sendMessage({ text: value });
    setInput("");
  }

  return (
    <section className="flex h-full flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-sm font-semibold tracking-tight">Agent chat</h1>
          <p className="text-xs text-muted-foreground">
            Describe what you want built — review the plan before anything ships.
          </p>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md space-y-4 pt-10 text-center">
            <h2 className="text-lg font-semibold">What should we build today?</h2>
            <p className="text-sm text-muted-foreground">
              The agent drafts a plan; you approve it; then you watch it execute.
            </p>
            <div className="space-y-2 text-left">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => submit(s)}
                  className="block w-full rounded-lg border border-border bg-card p-3 text-sm text-card-foreground transition-colors hover:bg-muted"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={
              m.role === "user" ? "flex justify-end" : "flex justify-start"
            }
          >
            <div
              className={
                m.role === "user"
                  ? "max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground"
                  : "max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-sm text-foreground"
              }
            >
              <p className="whitespace-pre-wrap">{messageText(m)}</p>
              {m.parts.some((p) => p.type === "data-plan") && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Plan ready — see the approval panel on the right.
                </p>
              )}
            </div>
          </div>
        ))}

        {status === "submitted" && (
          <p className="text-sm text-muted-foreground">Thinking…</p>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-border px-6 py-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
          className="flex items-end gap-2"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(input);
              }
            }}
            rows={1}
            placeholder="Describe a site or change…"
            className="max-h-40 min-h-10 flex-1 resize-none rounded-lg border border-border bg-card p-2.5 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <Button
            type="submit"
            size="icon-lg"
            disabled={busy || input.trim().length === 0}
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </Button>
        </form>
      </div>
    </section>
  );
}
