# Project Explanation — WordPress Automation Agent

A plain-language, file-by-file walkthrough of how this project actually works today (Sprints 1–6 complete, Sprint 7 next). For the "why we chose this stack" narrative see [project-overview.md](project-overview.md); for the raw directory tree see [project-structure.md](project-structure.md); for sprint-by-sprint history see [progress-tracker.md](progress-tracker.md). This file is the "how it all fits together."

---

## 1. The one-sentence version

You type a request in a chat UI ("build a 3-page portfolio site, dark theme, set up SEO"); a **Next.js** frontend sends it to a **FastAPI** backend; a **LangGraph** agent asks **Claude** to turn that into an ordered list of WordPress tool calls; the plan is shown back to you; **nothing touches the live WordPress site until you click Approve**; once approved, the same graph runs each tool call against WordPress over REST API / WP-CLI / SSH and streams the results back live.

---

## 2. The big picture (how the pieces talk to each other)

```
Browser (dashboard UI)
   │  useChat() posts messages
   ▼
Next.js API route  /api/chat  ───────────────┐
   │  starts a task                          │  (Next.js server-side proxy layer —
   ▼                                          │   browser never talks to FastAPI directly)
FastAPI  POST /api/tasks  ────────────────────┘
   │
   ▼
TaskManager.start()  →  compiled LangGraph orchestrator graph
   │
   ├─ plan_node     : Claude (via LangChain) picks WP tool calls → ordered plan
   ├─ approve_node  : graph calls interrupt(plan) and PAUSES here
   │                  (state is saved to Postgres via the checkpointer)
   ▼
Plan is returned to the browser → shown in the Approval Modal
   │
   │  user clicks Approve or Reject
   ▼
Next.js API route  /api/tasks/[id]/resume  ──▶  FastAPI POST /api/tasks/{id}/resume
   │
   ▼
TaskManager.resume_stream()  →  Command(resume="approve") wakes the paused graph
   │
   ├─ execute_node : for each planned step, run_approved() calls the real WP tool
   │                 with approved=True — this is the ONLY place that ever happens
   │                 → tool talks to WordPress via REST API / WP-CLI(SSH)
   │                 → each step streamed back as an ndjson event
   ├─ report_node  : final summary (applied/failed counts)
   ▼
Browser task log panel updates live, task status becomes "completed"
```

Two separate "brains" are involved and it's worth keeping them distinct:

- **Claude** does the *reasoning* — deciding which WordPress tools to call and generating content (page copy, Elementor layout structure, SEO text, theme choices).
- **The LangGraph graph** does the *control flow* — it's a deterministic state machine (`plan → approve → execute → report`) that Claude's output flows through. Claude never writes to WordPress directly; it only ever produces a tool call, and the graph decides whether/when that tool call is allowed to run.

---

## 3. The approval gate — the most important invariant in the codebase

Per [AGENTS.md](AGENTS.md) rule #1, no write ever reaches a live WordPress site without a human approving it first. This isn't just a UI convention — it's enforced at three layers simultaneously:

1. **Every write tool** in [backend/app/agent/tools/wp_tools.py](backend/app/agent/tools/wp_tools.py) takes an `approved: bool = False` argument. If it's `False`, the tool returns a `needs_approval` preview and does nothing — it never touches WordPress. (See `_needs_approval()`, [wp_tools.py:36](backend/app/agent/tools/wp_tools.py#L36).)
2. **`run_approved()`** in [backend/app/agent/wp_agent.py](backend/app/agent/wp_agent.py#L43) is the *only* function in the entire codebase allowed to set `approved=True`. Nothing else is permitted to do this.
3. **The orchestrator graph** in [backend/app/agent/orchestrator/graph.py](backend/app/agent/orchestrator/graph.py) calls LangGraph's `interrupt()` inside `approve_node` ([graph.py:53](backend/app/agent/orchestrator/graph.py#L53)), which physically pauses graph execution and persists its state to Postgres. The graph can only resume via an explicit `Command(resume="approve" | "reject")`. Only `"approve"` routes to `execute_node`, which is the only node that calls `run_approved`.

So the chain is: *interrupt pauses the graph* → *only an explicit approve resumes it* → *only the execute node calls run_approved* → *only run_approved sets approved=True* → *only then does a write tool touch WordPress.* A rejected plan makes zero tool calls, and this is unit-tested ([backend/tests/test_orchestrator_graph.py](backend/tests/test_orchestrator_graph.py)).

---

## 4. Backend deep dive (`backend/`, Python, FastAPI + LangGraph)

### 4.1 Entry point and wiring

[backend/app/main.py](backend/app/main.py) is where everything is assembled:
- On startup (`lifespan`), it opens a Postgres-backed LangGraph checkpointer ([app/agent/orchestrator/checkpointer.py](backend/app/agent/orchestrator/checkpointer.py)) so a paused (awaiting-approval) task survives a server restart. If Postgres isn't reachable it falls back to an in-memory checkpointer so the app still boots — but then a restart loses any paused task.
- It compiles the orchestrator graph (`build_orchestrator`) once and wraps it in a `TaskManager`, stored on `app.state.orchestrator`.
- It mounts three routers: `router` (health/ping), `wp_router` (raw WP CRUD test endpoints from Sprint 3), and `task_router` (the real `/api/tasks` flow from Sprint 4).
- CORS is configured from `settings.cors_origin_list` so the Next.js dev server can call it directly for the Sprint-1 `/ping` spike (the real task flow is proxied server-side and never hits CORS at all — see §6).

### 4.2 Config & secrets

[backend/app/config.py](backend/app/config.py) — a `pydantic-settings` `Settings` class. Everything that varies by environment (Anthropic API key, Postgres/Redis URLs, the Fernet `CREDENTIAL_ENCRYPTION_KEY`, model names, LangSmith key, CORS origins) is read from `backend/.env` (never committed — see `.env.example`). Nothing is hardcoded, per AGENTS.md rule #2.

[backend/app/crypto.py](backend/app/crypto.py) — Fernet encrypt/decrypt helpers. Used by the `EncryptedString` SQLAlchemy column type ([app/db/base.py](backend/app/db/base.py)) so WP site credentials are encrypted *at rest* in Postgres, not just in transit.

### 4.3 Data layer (`app/db/`)

- [app/db/models.py](backend/app/db/models.py) — two tables: `WpSite` (a site's slug, base URL, encrypted Application Password credentials, WP-CLI transport config) and `Task` (id, instruction, site_slug, status, timestamps — the orchestration bookkeeping row, separate from the LangGraph checkpoint itself).
- [app/db/session.py](backend/app/db/session.py) — async SQLAlchemy engine/session factory (`asyncpg` driver) used throughout the app.
- Migrations live in [backend/alembic/versions/](backend/alembic/versions/) — `0001_create_wp_sites.py`, `0002_create_tasks.py`.

### 4.4 WordPress integration layer (`app/wp/`)

This is the layer that actually talks to a WordPress site, split into three independent channels per AGENTS.md's integration rules — **never mixed**:

| Channel | File | Used for |
|---|---|---|
| REST API | [app/wp/rest_client.py](backend/app/wp/rest_client.py) | Pages, posts, media, menus, Elementor `_elementor_data`, post-meta (SEO). Auth via WP Application Passwords. |
| WP-CLI (SSH or local docker) | [app/wp/wpcli.py](backend/app/wp/wpcli.py) | Plugin install/activate/search, `wp elementor flush-css`, theme mods/options. Pluggable transport: real sites use Fabric/Paramiko SSH; the local Docker sandbox uses `docker exec` into the `wpcli` compose service (the Apache WP container has no sshd). |
| Credentials | [app/wp/credentials.py](backend/app/wp/credentials.py) | Fetches a site's row from Postgres and decrypts it into a `SiteCredentials` object that both the REST client and WP-CLI executor consume. |
| Schemas | [app/wp/schemas.py](backend/app/wp/schemas.py) | Pydantic models for both channels — `SiteCredentials`, `ContentCreate`/`ContentUpdate`, WP-CLI result shapes. |

Theme file edits (`functions.php`, custom widgets) would go through Fabric/Paramiko file operations directly — this channel is defined in the architecture but no skill currently exercises it (theming so far uses WP-CLI theme mods, not raw file edits).

### 4.5 Typed agent tools (`app/agent/tools/wp_tools.py`)

Every capability the agent can invoke is a typed LangChain `@tool` function in [backend/app/agent/tools/wp_tools.py](backend/app/agent/tools/wp_tools.py) — **17 tools total**:

- **Read tools** (run freely, no approval needed): `wp_list_pages`, `wp_get_page`, `wp_list_posts`, `wp_list_menus`, `wp_search_plugins`.
- **Write tools** (gated on `approved=True`): `wp_create_page`, `wp_update_page`, `wp_delete_page`, `wp_create_post`, `wp_install_plugin`, `wp_activate_plugin`, `wp_flush_elementor_css`, `wp_create_elementor_page`, `wp_publish_post`, `wp_apply_seo`, `wp_apply_theme`, `wp_configure_plugin`.

Each tool has an explicit typed signature (so Claude's tool-calling is constrained to valid arguments) and returns a JSON-serializable dict. `WP_TOOLS` (all of them) is what gets bound to the Claude model for planning; `WRITE_TOOLS` is the subset the approval gate cares about.

### 4.6 The orchestrator graph (`app/agent/orchestrator/`) — Sprint 4, the core

This is the actual LangGraph state machine. Four files matter most:

- [state.py](backend/app/agent/orchestrator/state.py) — defines `OrchestratorState` (the TypedDict threaded through the whole graph and persisted by the checkpointer: instruction, site_slug, plan, decision, results, report, status), `PlannedStep` (one planned tool call with a UI-facing title/preview/channel), and `ExecEvent` (a streamed execution event, mirroring the frontend's `ToolLogEntry` type exactly).
- [planner.py](backend/app/agent/orchestrator/planner.py) — `LLMPlanner.plan()` sends the instruction to Claude (via `langchain_anthropic.ChatAnthropic`) with `WP_TOOLS` bound. Claude can emit *multiple* tool calls in one response, and each becomes one `PlannedStep` in order (e.g. "install plugin" then "create page"). For every write step it also calls the tool once *without* approval to get a `needs_approval` preview — this is what the approval modal shows as a diff, and it happens without touching the site.
- [graph.py](backend/app/agent/orchestrator/graph.py) — builds the `StateGraph`: `plan_node` (calls the planner) → `approve_node` (calls `interrupt()`, pauses) → conditional edge → `execute_node` (loops over the plan calling `run_approved` per step, emitting a stream event per step via `get_stream_writer()`) → `report_node` (final tallies) → `END`.
- [manager.py](backend/app/agent/orchestrator/manager.py) — `TaskManager` is the runtime wrapper the API routes call. `start()` creates a task row, runs the graph up to the interrupt, and returns the plan. `resume_stream()` sends `Command(resume=decision)` and streams every custom event the graph emits (`stream_mode="custom"`) as ndjson, followed by a final report event. Because the checkpoint's `thread_id` is set to the task id, `get_plan()` can re-find a paused task even after a server restart.
- [checkpointer.py](backend/app/agent/orchestrator/checkpointer.py) — wraps `AsyncPostgresSaver` so graph state (including paused/interrupted state) survives restarts.
- [tasks_service.py](backend/app/agent/orchestrator/tasks_service.py) — plain CRUD against the `tasks` Postgres table (separate from, but referencing the same id as, the LangGraph checkpoint).

### 4.7 API routes (`app/api/`)

- [routes.py](backend/app/api/routes.py) — `/health`, `POST /api/ping` (the Sprint-1 spike, still alive at `/ping` in the frontend).
- [wp_routes.py](backend/app/api/wp_routes.py) — `/api/wp/sites`, `/api/wp/plan`, `/api/wp/execute` — the Sprint 3 single-tool-call NL path (`wp_agent.py`'s `WpAgent`), superseded by the real orchestrator for the main dashboard flow but still present/tested.
- [task_routes.py](backend/app/api/task_routes.py) — the real flow: `POST /api/tasks` (start, returns plan), `GET /api/tasks/{id}` (re-fetch plan/status), `POST /api/tasks/{id}/resume` (approve/reject, streams ndjson execution events via `StreamingResponse`).

### 4.8 Skills (`app/agent/skills/`) — the content-generation building blocks

A "skill" is a self-contained brief → structured-output → WordPress-write pipeline that a tool wraps. Four exist:

**Elementor (`skills/elementor/`) — Sprint 5, the highest-risk piece.** Because Elementor's `_elementor_data` JSON schema is undocumented and version-sensitive (AGENTS.md rule #3), Claude is **never** allowed to hand-write that JSON. Instead:
1. [schema.py](backend/app/agent/skills/elementor/schema.py) defines a small, constrained `PageSpec`/`SectionSpec` intermediate representation (IR) — just "which sections, what content goes in which slot."
2. [generator.py](backend/app/agent/skills/elementor/generator.py) asks Claude to fill that IR from a brief (structured output, not raw JSON).
3. [library.py](backend/app/agent/skills/elementor/library.py) loads real, hand-seeded section templates from [examples/](backend/app/agent/skills/elementor/examples/) (hero/features/pricing/contact/footer).
4. [builder.py](backend/app/agent/skills/elementor/builder.py) is deterministic code that clones the matching template, fills content tokens, regenerates unique element ids, and assembles the final `_elementor_data` — Claude never touches the JSON directly.
5. [validator.py](backend/app/agent/skills/elementor/validator.py) does structural + semantic checks (unique ids, valid nesting, column sums) before anything is allowed to write.
6. [skill.py](backend/app/agent/skills/elementor/skill.py) ties generate → build → validate into one `generate_elementor_page()` call, raising `ElementorValidationError` rather than ever writing bad data.

The `wp_create_elementor_page` tool ([wp_tools.py:210](backend/app/agent/tools/wp_tools.py#L210)) calls this pipeline, writes the page via REST, then **always** runs `wp elementor flush-css` via WP-CLI afterward — a layout write is considered incomplete without that flush (AGENTS.md's integration rule).

**Content (`skills/content/`) — Sprint 6.** Brief → `PostDraft` (title/body/category/tag suggestions) via Claude. The `wp_publish_post` tool find-or-creates categories/tags by name via the REST client (`ensure_categories`/`ensure_tags`) and optionally schedules via WP's `future` status + a date.

**SEO (`skills/seo/`) — Sprint 6.** Subject → meta title/description + JSON-LD via Claude, mapped to either Yoast or RankMath's specific post-meta keys (`seo_to_meta`, provider-selectable). Written via REST post-meta by `wp_apply_seo`. Depends on the companion WP plugin registering those meta keys with `show_in_rest` — otherwise WordPress silently drops them.

**Theme (`skills/theme/`) — Sprint 6.** Brief → `ThemeSpec` (palette/fonts/footer) via Claude, applied via WP-CLI theme mods/options plus a best-effort merge into the Elementor global kit. Driven by `wp_apply_theme`.

**Plugins (`skills/plugins/`) — Sprint 6.** A small hand-maintained recommendation catalog (`recommend_plugin`) plus WP-CLI search/configure (`wp_search_plugins` read, `wp_configure_plugin` write, on top of the Sprint-3 install/activate tools).

### 4.9 Background jobs (`app/worker/`)

[celery_app.py](backend/app/worker/celery_app.py) + [tasks.py](backend/app/worker/tasks.py) — a Celery app (Redis broker/backend) and an `execute_task` job that resumes a persisted task off the HTTP request path. Currently scaffolding: the live dashboard demo path runs the resume inline (inside the HTTP request) so it can stream live to the browser; Celery is wired and ready for genuinely long-running jobs but isn't in the critical path yet.

### 4.10 Tests

[backend/tests/](backend/tests/) mirrors the app structure — unit tests mock httpx (`respx`), SSH/subprocess, the LLM, and the DB (so the whole suite is green without Docker); `backend/tests/integration/` holds `@pytest.mark.integration` tests that self-skip unless a real Docker/Postgres/WordPress stack is up (e.g. [test_live_wp.py](backend/tests/integration/test_live_wp.py), [test_orchestrator_persistence.py](backend/tests/integration/test_orchestrator_persistence.py)). Current count: **89 passing, 7 skipped.**

---

## 5. Frontend deep dive (`frontend/`, Next.js + React + Zustand + TanStack Query)

### 5.1 The dashboard shell

[frontend/src/app/page.tsx](frontend/src/app/page.tsx) is the whole UI: a 4-way layout of `AppSidebar` (project list), `ChatPanel` (the conversation), `TaskLogPanel` (live tool-call log), and `ApprovalModal` (the gate) — all reading/writing one shared Zustand store.

### 5.2 State (`src/store/task-store.ts`)

[store/task-store.ts](frontend/src/store/task-store.ts) is the single source of truth for "where is the active task right now": `idle → planning → awaiting_approval → executing → completed | rejected`, plus the current `plan` and the streaming `log` of tool events. Two things write to it:
- `proposePlan()` — called by the chat panel when a plan arrives.
- `resumeTask(decision)` — called by the approval modal's Approve/Reject buttons. It POSTs to the resume proxy, reads the response body as an ndjson stream, and pushes each `tool` event into `log` and the final `report` event into `status`.

### 5.3 Chat flow (`src/components/dashboard/chat-panel.tsx` + `src/app/api/chat/route.ts`)

[chat-panel.tsx](frontend/src/components/dashboard/chat-panel.tsx) uses the Vercel AI SDK's `useChat` hook, posting to the local Next.js route `/api/chat`. That route ([app/api/chat/route.ts](frontend/src/app/api/chat/route.ts)) is **not** an AI SDK model call — it's a proxy: it takes the last user message, POSTs `{ instruction, site_slug }` to the real FastAPI `POST /api/tasks`, and re-streams the result back as a normal AI SDK UI message stream (some intro text) plus one typed custom part, `data-plan`, carrying the actual `Plan` object (including the backend `task_id`). The chat panel watches incoming messages for a `data-plan` part and calls `proposePlan()` the first time it sees one per message ([chat-panel.tsx:38](frontend/src/components/dashboard/chat-panel.tsx#L38)).

### 5.4 Approval flow (`src/components/dashboard/approval-modal.tsx` + `src/app/api/tasks/[id]/resume/route.ts`)

The modal opens automatically whenever `status === "awaiting_approval"`. It renders `plan.steps` (title, channel badge, and a JSON diff preview if the backend supplied one) and wires Approve/Reject to `resumeTask()`. That function POSTs to the local route [app/api/tasks/[id]/resume/route.ts](frontend/src/app/api/tasks/[id]/resume/route.ts), which is a pure pipe: it forwards the decision to FastAPI's `POST /api/tasks/{id}/resume` and streams the raw ndjson response body straight back to the browser untouched.

### 5.5 Types (`src/lib/types.ts`)

[lib/types.ts](frontend/src/lib/types.ts) defines the shared shapes: `Plan`/`PlanStep` (what the chat proxy emits and the modal renders), `ToolLogEntry` (mirrors the backend's `ExecEvent` field-for-field), `TaskStatus`, `WpChannel` ("REST API" | "WP-CLI" | "File ops"), and `ChatUIMessage` (the AI SDK message type parameterized with the custom `data-plan` part).

### 5.6 Supporting pieces

- [lib/backend.ts](frontend/src/lib/backend.ts) — `BACKEND_URL` (server-side only; `http://backend:8000` inside Docker, `localhost:8000` locally) and `DEFAULT_SITE_SLUG`. The browser never sees or calls `BACKEND_URL` directly — only the Next.js API routes do, running server-side.
- [components/providers.tsx](frontend/src/components/providers.tsx) — wraps the app in a TanStack Query client provider.
- [lib/use-projects.ts](frontend/src/lib/use-projects.ts) + [app/api/projects/route.ts](frontend/src/app/api/projects/route.ts) — the sidebar's project list; **still mocked** ([lib/mock-data.ts](frontend/src/lib/mock-data.ts)) — this is the one remaining non-real piece of the frontend.
- [app/ping/page.tsx](frontend/src/app/ping/page.tsx) — the original Sprint-1 spike, kept alive as a standalone route for a raw backend round-trip check, separate from the main dashboard.
- `src/components/ui/` — hand-built shadcn-style primitives (Button, Card, Badge, Separator, Dialog) on Base UI + class-variance-authority, styled entirely through design tokens (no hardcoded hex/Tailwind color classes, per AGENTS.md rule #7).

---

## 6. How the frontend actually connects to the backend

This is worth calling out explicitly since it's a common point of confusion:

- **The browser never talks to FastAPI directly** for the real task flow. It only ever calls Next.js's own API routes (`/api/chat`, `/api/tasks/[id]/resume`), which run **server-side** inside the Next.js process and proxy to FastAPI using `BACKEND_URL`. This is why there's no CORS concern for the main flow — CORS in [app/main.py](backend/app/main.py) exists only for the legacy `/ping` spike, which the browser does call directly via `NEXT_PUBLIC_API_BASE`.
- The two Next.js proxy routes exist specifically so the Python backend's wire format (raw JSON, ndjson streaming) never has to match the Vercel AI SDK's UI-message-stream format — the proxy layer translates between them, keeping Python and TypeScript "cleanly separated at the REST/WebSocket boundary" per AGENTS.md rule #5.
- The `task_id` returned by `POST /api/tasks` is the thread id LangGraph uses for its Postgres checkpoint — it's the single piece of state that ties a browser session to a specific paused/resumable graph run.

---

## 7. What's real vs. what's still a stand-in, right now

| Area | Status |
|---|---|
| Chat → plan → approve → execute → report | **Real**, full round trip through FastAPI/LangGraph/Postgres (Sprint 4) |
| WP REST + WP-CLI tool layer | **Real** (Sprint 3), 17 typed tools |
| Elementor page generation | **Real pipeline**, but the section templates in `examples/` are hand-seeded reference scaffolds, not genuine Elementor editor exports yet — flagged as a Sprint 5 follow-up |
| Content / SEO / theme / plugin skills | **Real** (Sprint 6), each individually evaluated; SEO/theme meta persistence depends on the (not-yet-built) companion WP plugin registering custom meta/`show_in_rest` |
| Sidebar project list | **Mocked** — `/api/projects` still serves `mock-data.ts` |
| Celery worker | **Scaffolded**, not yet in the critical path (demo path runs inline so it can stream) |
| Multi-page/composite briefs ("build a 5-page site") | **Not yet** — each skill works individually; ordering multiple skills into one dependency-aware run is Sprint 7 |

---

## 8. The plan from here (Sprints 7–10)

- **Sprint 7 (next up) — multi-step task decomposition.** Right now the planner turns one instruction into a flat list of tool calls in one Claude response. Sprint 7 adds a higher-level planning step that can decompose a full brief ("5-page site") into a dependency-ordered task graph (theme before content, pages before menu assembly), plus a rollback/snapshot mechanism (WP DB export before major writes) and clear partial-failure surfacing instead of silently continuing.
- **Sprint 8 — eval suite & quality scoring.** A golden dataset of 20+ real scenarios run against the sandboxed Docker WP instance, Playwright visual regression, and CI gating so no PR can regress a skill's score.
- **Sprint 9 — security hardening.** Confirming the agent truly cannot run arbitrary PHP/shell beyond the allow-listed WP-CLI commands, adding rate limits/cost controls, revisiting credential storage (Vault at scale), and enforcing staging-before-production.
- **Sprint 10 — beta launch.** Running real projects through the agent with a human on every approval gate, then feeding failure modes back into the Sprint 5/6 skills.

The sequencing logic (from [progress-tracker.md](progress-tracker.md)): Sprint 5 (Elementor) was treated as the bottleneck because every later skill depends on the agent reliably producing valid layouts; Sprint 4 replaced Sprint 2's mocked approval UI with the real LangGraph interrupt; evals (Sprint 8) intentionally come after the skills exist rather than being guessed at up front; Sprint 10 is explicitly a "backlog-generating" pass, not a wrap-up.

---

## 9. Quick reference — "what do I touch for X?"

| I want to... | Look at |
|---|---|
| Change what the agent is allowed to do to WordPress | [backend/app/agent/tools/wp_tools.py](backend/app/agent/tools/wp_tools.py) |
| Change how a plan is generated from an instruction | [backend/app/agent/orchestrator/planner.py](backend/app/agent/orchestrator/planner.py) |
| Change the approve/execute/report control flow | [backend/app/agent/orchestrator/graph.py](backend/app/agent/orchestrator/graph.py) |
| Add a new WordPress capability ("skill") | new folder under [backend/app/agent/skills/](backend/app/agent/skills/), then a gated tool in `wp_tools.py` |
| Change Elementor section templates | [backend/app/agent/skills/elementor/examples/](backend/app/agent/skills/elementor/examples/) (validate via `builder.py`/`validator.py` tests first) |
| Change the REST payloads sent to WordPress | [backend/app/wp/rest_client.py](backend/app/wp/rest_client.py) |
| Change WP-CLI commands / add a new one | [backend/app/wp/wpcli.py](backend/app/wp/wpcli.py) |
| Change the dashboard UI | [frontend/src/components/dashboard/](frontend/src/components/dashboard/) |
| Change how the browser reaches FastAPI | [frontend/src/app/api/](frontend/src/app/api/) (the proxy routes) + [frontend/src/lib/backend.ts](frontend/src/lib/backend.ts) |
| Change live task/plan state on the frontend | [frontend/src/store/task-store.ts](frontend/src/store/task-store.ts) |
| Add/rotate a secret | `backend/.env` / `frontend/.env` (never committed — see `.env.example` in each) |
