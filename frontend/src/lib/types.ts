// Shared types for the dashboard. The agent/backend is mocked in Sprint 2;
// these shapes mirror what the real LangGraph orchestrator will emit later
// (a plan to approve, then a stream of tool-call results).

import type { UIMessage } from "ai";

/** Which WordPress integration channel a step writes through. */
export type WpChannel = "REST API" | "WP-CLI" | "File ops";

/** A single planned change the agent intends to make. */
export type PlanStep = {
  id: string;
  title: string;
  description: string;
  tool: string; // e.g. "wp.createPage"
  channel: WpChannel;
  /** Human-readable preview of the change (shown in the approval modal). */
  diff?: string;
};

/** The plan the agent proposes before any write happens. */
export type Plan = {
  summary: string;
  steps: PlanStep[];
};

/** Data parts the chat stream can emit (typed `data-plan`). */
export type ChatDataParts = {
  plan: Plan;
};

/** Our concrete UIMessage type, carrying the typed `data-plan` part. */
export type ChatUIMessage = UIMessage<unknown, ChatDataParts>;

/** One entry in the live task log — a tool call and its result. */
export type ToolLogEntry = {
  id: string;
  stepId: string;
  tool: string;
  channel: WpChannel;
  status: "running" | "success" | "error";
  message: string;
  at: number;
};

/** Lifecycle of the active task, surfaced in the UI. */
export type TaskStatus =
  | "idle"
  | "planning"
  | "awaiting_approval"
  | "executing"
  | "completed"
  | "rejected";

/** A WordPress site/project shown in the sidebar. */
export type Project = {
  id: string;
  name: string;
  url: string;
  status: "active" | "draft";
  pages: number;
};
