# Project Structure

This document describes the layout of the **WordPress Automation** repository — an AI agent system that builds and manages WordPress/Elementor sites from natural-language instructions. For the intended end-state architecture and the role each technology plays, see [project-overview.md](project-overview.md).

> **Current state:** Sprints 1–4 complete. The backend has a LangGraph "ping" node (Sprint 1); a typed WordPress tool layer — REST client, pluggable WP-CLI executor, encrypted credentials, approval-gated tools (Sprint 3); and a real orchestration graph (`plan → approve[interrupt] → execute → report`) with Postgres-checkpointed state, `/api/tasks` endpoints, and a Celery worker (Sprint 4). The frontend dashboard (Sprint 2) is now wired off its mocks onto that real interrupt/resume flow. The whole stack boots via Docker Compose. Items marked _(planned)_ come from the overview but are not yet implemented.

## Top-level layout

```
wordpress-automation/
├── AGENTS.md              # Agent working rules for this repo
├── CLAUDE.md              # Claude Code instructions — imports AGENTS.md
├── project-overview.md    # Intended architecture & rationale (the "why")
├── project-structure.md   # This file (the "where")
├── progress-tracker.md    # Sprint plan & current status
├── docker-compose.yml     # One-command dev stack (see below)
├── .env.example           # Root quick-start / compose notes
├── .gitignore             # Ignores .env files, venvs, node_modules, build output
├── backend/               # FastAPI + LangGraph agent server (Python)
└── frontend/              # Next.js dashboard / chat UI (TypeScript)
```

The repo is split into two independently-managed apps: a **Python backend** (`uv`-managed) and a **TypeScript frontend** (`npm`-managed). There is no shared root package manager. Docker Compose ties them together with the data and WordPress services for local dev.

## Dev environment (Docker Compose)

`docker compose up --build` brings up the full stack from one command:

| Service | Image / build | Port | Role |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | App database + embeddings (pgvector) |
| `redis` | `redis:7-alpine` | 6379 | Celery broker/result store _(used in later sprints)_ |
| `wp-db` | `mariadb:11` | — | Database for the WordPress instance |
| `wordpress` | `wordpress:6-php8.3-apache` | 8080 | Local sandbox WP site (the agent's target) |
| `wp-init` | `wordpress:cli-php8.3` | — | One-shot: installs WP + activates Elementor, then exits |
| `wpcli` | `wordpress:cli-php8.3` | — | Persistent WP-CLI container; `docker exec` target for the local WP-CLI transport |
| `backend` | `./backend` | 8000 | FastAPI + LangGraph agent |
| `worker` | `./backend` | — | Celery worker — long-running orchestration execution |
| `frontend` | `./frontend` | 3000 | Next.js dashboard |

Secrets are supplied via `backend/.env` (copy from `backend/.env.example`); the Anthropic API key and the `CREDENTIAL_ENCRYPTION_KEY` are never hardcoded. The `wp-init` script lives inline in `docker-compose.yml` as a Compose `config`.

## Backend (`backend/`)

FastAPI server that receives requests from the frontend and routes them into the LangGraph agent, which orchestrates Claude and WordPress tooling.

```
backend/
├── .python-version        # Pins Python 3.14
├── pyproject.toml         # Project metadata + dependencies (uv/PEP 621)
├── uv.lock                # Locked dependency graph (uv)
├── Dockerfile             # Backend image (uv-based, Python 3.14)
├── .dockerignore          # Excludes .venv, caches, .env from the image
├── .env.example           # Env template (ANTHROPIC_API_KEY, CREDENTIAL_ENCRYPTION_KEY, …)
├── README.md              # (empty)
├── main.py                # Local launcher — runs uvicorn against app.main:app
├── alembic.ini            # Alembic config (DB URL injected from settings)
├── alembic/
│   ├── env.py             # Async migration environment (uses Base metadata)
│   ├── script.py.mako     # Migration template
│   └── versions/
│       ├── 0001_create_wp_sites.py   # Schema: wp_sites
│       └── 0002_create_tasks.py      # Schema: tasks (orchestration metadata)
├── tests/                 # pytest suite (unit + gated integration)
│   ├── conftest.py        # Sets a throwaway encryption key before app import
│   ├── test_crypto.py     # Fernet encrypt/decrypt
│   ├── test_rest_client.py# WP REST CRUD (respx-mocked httpx)
│   ├── test_wpcli.py      # WP-CLI executors (mocked subprocess/Fabric)
│   ├── test_tools.py      # Typed tools + the approval gate
│   ├── test_wp_agent.py   # Gated NL agent path (LLM mocked)
│   ├── test_orchestrator_graph.py # Graph: interrupt/approve/reject (MemorySaver)
│   ├── test_task_manager.py       # TaskManager start/resume (DB mocked)
│   ├── test_planner.py            # LLM planner → ordered steps (LLM mocked)
│   ├── test_task_routes.py        # /api/tasks HTTP contract (TestClient)
│   └── integration/
│       ├── test_live_wp.py               # @integration — live Docker WP (self-skips)
│       └── test_orchestrator_persistence.py # @integration — paused task survives restart
└── app/
    ├── __init__.py
    ├── main.py            # FastAPI app: CORS + routers + lifespan (checkpointer/graph)
    ├── config.py          # pydantic-settings Settings (secrets via env/.env)
    ├── crypto.py          # Fernet encrypt/decrypt for credentials at rest
    ├── api/
    │   ├── __init__.py
    │   ├── routes.py      # /health and POST /api/ping
    │   ├── wp_routes.py   # /api/wp/sites, /api/wp/plan, /api/wp/execute
    │   └── task_routes.py # /api/tasks (start), /{id} (detail), /{id}/resume (stream)
    ├── db/
    │   ├── __init__.py
    │   ├── base.py        # DeclarativeBase + EncryptedString column type
    │   ├── session.py     # Async engine + session factory + get_session dep
    │   └── models.py      # WpSite + Task models
    ├── wp/
    │   ├── __init__.py
    │   ├── schemas.py     # SiteCredentials + REST/CLI Pydantic models
    │   ├── rest_client.py # Async WP REST client (App Password auth)
    │   ├── wpcli.py       # Pluggable WP-CLI executor (SSH / local docker)
    │   └── credentials.py # Store/fetch/decrypt per-site credentials
    ├── agent/
    │   ├── __init__.py
    │   ├── graph.py       # LangGraph "ping" node (Sprint 1)
    │   ├── wp_agent.py    # Approval-gated NL → one tool call; run_approved()
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   └── wp_tools.py# Typed WP tools; writes require approved=True
    │   └── orchestrator/  # Sprint 4 state machine
    │       ├── __init__.py
    │       ├── state.py       # OrchestratorState + PlannedStep + ExecEvent
    │       ├── planner.py     # NL → ordered list of tool calls (LLM)
    │       ├── graph.py       # plan → approve(interrupt) → execute → report
    │       ├── checkpointer.py# AsyncPostgresSaver factory (persistence)
    │       ├── manager.py     # TaskManager: start→interrupt, resume+stream
    │       └── tasks_service.py # tasks table CRUD
    └── worker/
        ├── __init__.py
        ├── celery_app.py  # Celery app (Redis broker/backend)
        └── tasks.py       # execute_task — resume a paused task in a worker
```

- **Package manager:** [`uv`](https://github.com/astral-sh/uv) (`uv.lock`, `pyproject.toml`), Python `>=3.14`. Test deps (`pytest`, `pytest-asyncio`, `respx`) are in the `dev` dependency group.
- **Dependencies:** all declared in `pyproject.toml` — `fastapi[standard]`, `langgraph`, `langgraph-checkpoint-postgres`, `anthropic`, `langchain-anthropic`, `sqlalchemy`/`asyncpg`/`psycopg`/`alembic`/`pgvector`, `redis`/`celery`, `fabric`/`paramiko`, `httpx`, `cryptography`, `pydantic-settings`.
- **Entry point:** [backend/app/main.py](backend/app/main.py) — FastAPI app, CORS, and the API + WP routers. [backend/main.py](backend/main.py) is a thin uvicorn launcher.
- **WordPress integration ([app/wp/](backend/app/wp/)):** REST client for content (posts/pages/media/menus); a pluggable WP-CLI executor (Fabric/Paramiko SSH for real sites, `docker exec` for the local sandbox) for installs/activation/`elementor flush-css`; encrypted per-site credential storage.
- **Agent tools ([app/agent/tools/wp_tools.py](backend/app/agent/tools/wp_tools.py)):** each capability is a typed LangChain `@tool`. Read tools run freely; **write tools refuse to act unless `approved=True`**. `run_approved` (in [wp_agent.py](backend/app/agent/wp_agent.py)) is the only path that grants approval, and the orchestrator's execute node is the only caller.
- **Orchestration graph ([app/agent/orchestrator/](backend/app/agent/orchestrator/)):** the Sprint 4 state machine `plan → approve → execute → report`. `approve` calls `interrupt(plan)` so the graph pauses with state persisted by `AsyncPostgresSaver`; a `Command(resume=decision)` continues it. `TaskManager` starts a run to the interrupt and resumes it, streaming a live event per tool call. The checkpoint thread id = the task id, so a paused task survives a restart. `/api/tasks` exposes start/detail/resume; the Next.js routes proxy to them.
- **Celery worker ([app/worker/](backend/app/worker/)):** scaffolding for long-running execution — `execute_task` resumes a persisted task off the request path against the shared Postgres checkpoint. The Sprint 4 demo path runs inline (so it streams live); the worker is ready for genuinely long jobs.
- **Config / secrets:** [backend/app/config.py](backend/app/config.py) reads all settings (API key, models, DB/Redis URLs, `CREDENTIAL_ENCRYPTION_KEY`, Celery URLs, optional `LANGSMITH_API_KEY`, CORS) from the environment / `.env`. Credentials are Fernet-encrypted at rest; nothing is hardcoded.
- **Tests:** `pytest` — unit tests mock httpx (`respx`), SSH/subprocess, the LLM, and the DB, and use `MemorySaver` for the graph, so they pass without Docker. Integration tests are `@pytest.mark.integration` and self-skip when Docker/Postgres/WP is unavailable. **38 passing, 4 skipped.**
- **Planned components** _(per overview, not yet present)_: Elementor JSON generation skill (Sprint 5), content/SEO/theming skills (Sprint 6), pgvector recall.

## Frontend (`frontend/`)

Next.js application serving the dashboard, chat interface, and live preview, streaming agent responses token-by-token.

```
frontend/
├── package.json           # Scripts + dependencies
├── package-lock.json      # Locked dependency graph (npm)
├── tsconfig.json          # TypeScript config — "@/*" → ./src/*
├── next.config.ts         # Next.js config (empty/default)
├── postcss.config.mjs     # PostCSS — loads @tailwindcss/postcss
├── eslint.config.mjs      # Flat ESLint config (next core-web-vitals + TS)
├── components.json        # shadcn/ui config
├── Dockerfile             # Frontend image (Next.js dev server)
├── .dockerignore          # Excludes node_modules, .next, .env from the image
├── .env.example           # Env template (NEXT_PUBLIC_API_BASE)
├── next-env.d.ts          # Next.js generated types (not tracked)
├── README.md              # Default create-next-app readme
├── public/                # Static assets (next.svg, vercel.svg, file.svg, globe.svg, window.svg)
└── src/
    ├── app/               # Next.js App Router
    │   ├── layout.tsx     # Root layout — fonts, global CSS, <Providers>
    │   ├── page.tsx       # Dashboard: sidebar + chat + task log + approval modal
    │   ├── globals.css    # Tailwind import + design-token CSS variables
    │   ├── favicon.ico
    │   ├── ping/
    │   │   └── page.tsx   # Sprint 1 ping spike (backend round-trip), kept at /ping
    │   └── api/           # Next route handlers (proxy to FastAPI; projects still mock)
    │       ├── chat/route.ts               # useChat → starts a real task; streams text + data-plan
    │       ├── tasks/[id]/resume/route.ts  # proxies approve/reject; pipes the exec ndjson stream
    │       └── projects/route.ts           # project/site list for the sidebar (mock)
    ├── components/
    │   ├── providers.tsx          # TanStack Query client provider
    │   ├── dashboard/
    │   │   ├── app-sidebar.tsx    # Sidebar + project list (TanStack Query)
    │   │   ├── chat-panel.tsx     # useChat chat UI; sends siteSlug; surfaces plans
    │   │   ├── approval-modal.tsx # Approval gate — approve/reject → resumeTask()
    │   │   └── task-log-panel.tsx # Live tool-call log + task status
    │   └── ui/                    # shadcn-style primitives (Base UI + CVA, tokens)
    │       ├── button.tsx
    │       ├── card.tsx
    │       ├── badge.tsx
    │       ├── separator.tsx
    │       └── dialog.tsx
    ├── store/
    │   └── task-store.ts          # Zustand live task state + resumeTask() stream reader
    └── lib/
        ├── utils.ts               # cn() class-merge helper
        ├── backend.ts             # Server-side BACKEND_URL + DEFAULT_SITE_SLUG
        ├── types.ts               # Plan / ToolLogEntry / Project / ChatUIMessage types
        ├── mock-data.ts           # Mock projects for the sidebar
        └── use-projects.ts        # TanStack Query hook for the project list
```

- **Framework:** Next.js `16.2.9` (App Router), React `19.2.4`. _Note: the overview refers to "Next.js 14"; the installed version is 16.x._
- **Package manager:** `npm` (`package-lock.json`).
- **Styling:** Tailwind CSS v4 via `@tailwindcss/postcss`, with theme variables in [globals.css](frontend/src/app/globals.css).
- **State / data:** Zustand `^5` drives live task state ([store/task-store.ts](frontend/src/store/task-store.ts)); TanStack Query `^5` fetches the project list ([lib/use-projects.ts](frontend/src/lib/use-projects.ts)) via the [Providers](frontend/src/components/providers.tsx) wrapper.
- **AI streaming:** Vercel AI SDK — `ai` `^6` + `@ai-sdk/react` `^3` (`useChat`). As of Sprint 4 the chat/approval routes are **real**: `/api/chat` starts a LangGraph task on FastAPI and streams its plan back as a `data-plan` part (carrying the task id); `/api/tasks/[id]/resume` proxies approve/reject and pipes the execution stream. Only `/api/projects` remains mock.
- **Backend URLs:** browser-facing `NEXT_PUBLIC_API_BASE` (ping spike) and server-side `BACKEND_URL` (the proxy target, `http://backend:8000` in Docker) — see [lib/backend.ts](frontend/src/lib/backend.ts). `NEXT_PUBLIC_DEFAULT_SITE` selects the WP site slug.
- **Scripts:** `dev`, `build`, `start` (Next.js) and `lint` (ESLint).
- **Path alias:** `@/*` resolves to `frontend/src/*`.
- **Styling rule:** colors come from design tokens only (the CSS variables in `globals.css` / token classes like `bg-background`, `text-muted-foreground`) — no hardcoded hex or raw Tailwind color classes.
- **Planned components** _(per overview, not yet present)_: a real site selector (replacing the single default slug), live page preview panel.

## Documentation & agent files

| File | Purpose |
|------|---------|
| [project-overview.md](project-overview.md) | Narrative architecture — frontend, backend, and WordPress/Elementor integration layers, and the role of each tool. |
| [project-structure.md](project-structure.md) | This file — directory layout and current vs. planned state. |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Root agent instructions — `CLAUDE.md` imports `AGENTS.md`, which holds the working rules for this repo. |
| [progress-tracker.md](progress-tracker.md) | Sprint plan and current status; updated after every feature. |

## Notable observations

- **Sprints 1–4 complete:** Sprint 1 — the end-to-end path (frontend → FastAPI → LangGraph → Claude → back). Sprint 2 — the dashboard shell. Sprint 3 — a typed WP tool layer with encrypted credentials and code-level approval gating. Sprint 4 — a real orchestration graph whose `interrupt()` pauses for approval and resumes from the dashboard, with Postgres-persisted state.
- **One real approval gate now:** the graph pauses at `interrupt(plan)` and only `Command(resume="approve")` reaches the execute node, which is the sole caller of `run_approved` (the sole granter of `approved=True`). The Sprint 2 UI mock and the standalone `approved` flag are superseded by this single path. The Elementor JSON skill (Sprint 5) and pgvector recall remain target architecture in [project-overview.md](project-overview.md).
- **Version drift:** The overview describes "Next.js 14," but `package.json` pins `16.2.9`. Follow the installed version and its bundled docs.
- **Deps reconciled:** All backend dependencies (including `langgraph` and `anthropic`) now live in `pyproject.toml` / `uv.lock`; there is no separate `requirements.txt`.
