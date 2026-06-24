// Mocked projects endpoint — the sidebar's project list. TanStack Query fetches
// this. Later sprints back it with the real Postgres-stored site list.

import { NextResponse } from "next/server";

import { MOCK_PROJECTS } from "@/lib/mock-data";

export async function GET() {
  return NextResponse.json(MOCK_PROJECTS);
}
