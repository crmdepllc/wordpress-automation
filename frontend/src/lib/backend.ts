// Server-side base URL for the FastAPI backend. Used by the Next.js API routes
// that proxy to the real orchestration endpoints (browser never calls these
// directly). In Docker this is the compose service host; locally, localhost.

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// The WP site the dashboard operates on. A site selector is a later refinement;
// for now a single configurable default keeps the proxy end-to-end.
export const DEFAULT_SITE_SLUG =
  process.env.NEXT_PUBLIC_DEFAULT_SITE ?? "sandbox";
