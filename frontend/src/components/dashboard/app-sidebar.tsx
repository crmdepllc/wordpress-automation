"use client";

import { LayoutGrid, Plus, Sparkles } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useProjects } from "@/lib/use-projects";
import { useTaskStore } from "@/store/task-store";

export function AppSidebar() {
  const { data: projects, isLoading, isError } = useProjects();
  const reset = useTaskStore((s) => s.reset);

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 py-4">
        <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="size-4" />
        </span>
        <span className="text-sm font-semibold tracking-tight">WP Automation</span>
      </div>

      <Separator />

      <div className="px-3 py-3">
        <Button
          variant="default"
          size="lg"
          className="w-full"
          onClick={reset}
        >
          <Plus className="size-4" />
          New task
        </Button>
      </div>

      <div className="px-4 pb-2 pt-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Projects
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2">
        {isLoading && (
          <p className="px-2 py-1 text-sm text-muted-foreground">Loading…</p>
        )}
        {isError && (
          <p className="px-2 py-1 text-sm text-destructive">
            Couldn’t load projects.
          </p>
        )}
        {projects?.map((p) => (
          <button
            key={p.id}
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <LayoutGrid className="size-4 shrink-0 text-muted-foreground" />
            <span className="flex-1 truncate">{p.name}</span>
            <Badge variant={p.status === "active" ? "secondary" : "muted"}>
              {p.pages}
            </Badge>
          </button>
        ))}
      </nav>

      <Separator />

      <div className="px-3 py-3">
        <Link
          href="/ping"
          className="block rounded-lg px-2 py-2 text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        >
          Sprint 1 ping spike →
        </Link>
      </div>
    </aside>
  );
}
