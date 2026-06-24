"use client";

import { useQuery } from "@tanstack/react-query";

import type { Project } from "@/lib/types";

async function fetchProjects(): Promise<Project[]> {
  const res = await fetch("/api/projects");
  if (!res.ok) throw new Error("Failed to load projects");
  return res.json();
}

/** Project/site list for the sidebar, fetched via TanStack Query. */
export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: fetchProjects });
}
