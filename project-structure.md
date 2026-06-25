# Project Structure

This document describes the layout of the **WordPress Automation** repository — an AI agent system that builds and manages WordPress/Elementor sites from natural-language instructions. For the intended end-state architecture and the role each technology plays, see [project-overview.md](project-overview.md).

> **Current state:** Sprints 1–3 complete. The backend exposes a FastAPI app with a LangGraph "ping" node (Sprint 1); the frontend is a working dashboard shell against mocked routes (Sprint 2); and the backend now has a typed WordPress tool layer — async REST client, pluggable WP-CLI executor, encrypted per-site credential storage, and approval-gated LangGraph tools exposed through a thin NL agent path (Sprint 3). The whole stack boots via Docker Compose. Items marked _(planned)_ come from the overview but are not yet implemented.

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
│       └── 0001_create_wp_sites.py   # Initial schema: wp_sites
├── tests/                 # pytest suite (unit + gated integration)
│   ├── conftest.py        # Sets a throwaway encryption key before app import
│   ├── test_crypto.py     # Fernet encrypt/decrypt
│   ├── test_rest_client.py# WP REST CRUD (respx-mocked httpx)
│   ├── test_wpcli.py      # WP-CLI executors (mocked subprocess/Fabric)
│   ├── test_tools.py      # Typed tools + the approval gate
│   ├── test_wp_agent.py   # Gated NL agent path (LLM mocked)
│   └── integration/
│       └── test_live_wp.py# @integration — live Docker WP (self-skips)
└── app/
    ├── __init__.py
    ├── main.py            # FastAPI app: CORS + router mounts
    ├── config.py          # pydantic-settings Settings (secrets via env/.env)
    ├── crypto.py          # Fernet encrypt/decrypt for credentials at rest
    ├── api/
    │   ├── __init__.py
    │   ├── routes.py      # /health and POST /api/ping
    │   └── wp_routes.py   # /api/wp/sites, /api/wp/plan, /api/wp/execute
    ├── db/
    │   ├── __init__.py
    │   ├── base.py        # DeclarativeBase + EncryptedString column type
    │   ├── session.py     # Async engine + session factory + get_session dep
    │   └── models.py      # WpSite model (encrypted secret columns)
    ├── wp/
    │   ├── __init__.py
    │   ├── schemas.py     # SiteCredentials + REST/CLI Pydantic models
    │   ├── rest_client.py # Async WP REST client (App Password auth)
    │   ├── wpcli.py       # Pluggable WP-CLI executor (SSH / local docker)
    │   └── credentials.py # Store/fetch/decrypt per-site credentials
    └── agent/
        ├── __init__.py
        ├── graph.py       # LangGraph "ping" node (Sprint 1)
        ├── wp_agent.py    # Thin approval-gated NL → one tool call path
        └── tools/
            ├── __init__.py
            └── wp_tools.py# Typed WP tools; writes require approved=True
```

- **Package manager:** [`uv`](https://github.com/astral-sh/uv) (`uv.lock`, `pyproject.toml`), Python `>=3.14`. Test deps (`pytest`, `pytest-asyncio`, `respx`) are in the `dev` dependency group.
- **Dependencies:** all declared in `pyproject.toml` — `fastapi[standard]`, `langgraph`, `langgraph-checkpoint-postgres`, `anthropic`, `langchain-anthropic`, `sqlalchemy`/`asyncpg`/`psycopg`/`alembic`/`pgvector`, `redis`/`celery`, `fabric`/`paramiko`, `httpx`, `cryptography`, `pydantic-settings`.
- **Entry point:** [backend/app/main.py](backend/app/main.py) — FastAPI app, CORS, and the API + WP routers. [backend/main.py](backend/main.py) is a thin uvicorn launcher.
- **WordPress integration ([app/wp/](backend/app/wp/)):** REST client for content (posts/pages/media/menus); a pluggable WP-CLI executor (Fabric/Paramiko SSH for real sites, `docker exec` for the local sandbox) for installs/activation/`elementor flush-css`; encrypted per-site credential storage.
- **Agent tools ([app/agent/tools/wp_tools.py](backend/app/agent/tools/wp_tools.py)):** each capability is a typed LangChain `@tool`. Read tools run freely; **write tools refuse to act unless `approved=True`** — the code-level approval gate until Sprint 4's real interrupt graph. [wp_agent.py](backend/app/agent/wp_agent.py) turns NL into a single proposed tool call and is the only path that grants approval.
- **Config / secrets:** [backend/app/config.py](backend/app/config.py) reads all settings (API key, model names, DB/Redis URLs, `CREDENTIAL_ENCRYPTION_KEY`, CORS) from the environment / `.env`. Credentials are Fernet-encrypted at rest; nothing is hardcoded.
- **Tests:** `pytest` — unit tests mock httpx (`respx`) and SSH/subprocess so they pass without Docker; integration tests are marked `@pytest.mark.integration` and self-skip when the sandbox WP/Docker is unavailable.
- **Planned components** _(per overview, not yet present)_: full orchestration graph + real approval interrupt (Sprint 4), Elementor JSON skill (Sprint 5), pgvector recall, Redis/Celery job queue.

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
    │   └── api/           # Mocked backend routes for the Sprint 2 UI shell
    │       ├── chat/route.ts      # useChat endpoint — streams text + a data-plan part
    │       ├── execute/route.ts   # streams ndjson tool-log events after approval
    │       └── projects/route.ts  # project/site list for the sidebar
    ├── components/
    │   ├── providers.tsx          # TanStack Query client provider
    │   ├── dashboard/
    │   │   ├── app-sidebar.tsx    # Sidebar + project list (TanStack Query)
    │   │   ├── chat-panel.tsx     # useChat chat UI; surfaces plans for approval
    │   │   ├── approval-modal.tsx # Human approval gate — plan/diff, approve/reject
    │   │   └── task-log-panel.tsx # Live tool-call log + task status
    │   └── ui/                    # shadcn-style primitives (Base UI + CVA, tokens)
    │       ├── button.tsx
    │       ├── card.tsx
    │       ├── badge.tsx
    │       ├── separator.tsx
    │       └── dialog.tsx
    ├── store/
    │   └── task-store.ts          # Zustand live task state + runExecution() stream reader
    └── lib/
        ├── utils.ts               # cn() class-merge helper
        ├── types.ts               # Plan / ToolLogEntry / Project / ChatUIMessage types
        ├── mock-data.ts           # Mock projects + buildMockPlan()
        └── use-projects.ts        # TanStack Query hook for the project list
```

- **Framework:** Next.js `16.2.9` (App Router), React `19.2.4`. _Note: the overview refers to "Next.js 14"; the installed version is 16.x._
- **Package manager:** `npm` (`package-lock.json`).
- **Styling:** Tailwind CSS v4 via `@tailwindcss/postcss`, with theme variables in [globals.css](frontend/src/app/globals.css).
- **State / data:** Zustand `^5` drives live task state ([store/task-store.ts](frontend/src/store/task-store.ts)); TanStack Query `^5` fetches the project list ([lib/use-projects.ts](frontend/src/lib/use-projects.ts)) via the [Providers](frontend/src/components/providers.tsx) wrapper.
- **AI streaming:** Vercel AI SDK — `ai` `^6` (server stream helpers) + `@ai-sdk/react` `^3` (`useChat`). The chat panel streams from `/api/chat`; the plan arrives as a typed `data-plan` part. _Backend is mocked in Sprint 2; Sprint 4 swaps these routes for the real LangGraph interrupt/resume._
- **Backend URL:** `NEXT_PUBLIC_API_BASE` (defaults to `http://localhost:8000`) — set in `docker-compose.yml` and `frontend/.env.example`.
- **Scripts:** `dev`, `build`, `start` (Next.js) and `lint` (ESLint).
- **Path alias:** `@/*` resolves to `frontend/src/*`.
- **Styling rule:** colors come from design tokens only (the CSS variables in `globals.css` / token classes like `bg-background`, `text-muted-foreground`) — no hardcoded hex or raw Tailwind color classes.
- **Planned components** _(per overview, not yet present)_: full dashboard shell, chat interface, live preview panel, approval modals.

## Documentation & agent files

| File | Purpose |
|------|---------|
| [project-overview.md](project-overview.md) | Narrative architecture — frontend, backend, and WordPress/Elementor integration layers, and the role of each tool. |
| [project-structure.md](project-structure.md) | This file — directory layout and current vs. planned state. |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Root agent instructions — `CLAUDE.md` imports `AGENTS.md`, which holds the working rules for this repo. |
| [progress-tracker.md](progress-tracker.md) | Sprint plan and current status; updated after every feature. |

## Notable observations

- **Sprints 1–3 complete:** Sprint 1 — the end-to-end path (frontend → FastAPI → LangGraph → Claude → back) works. Sprint 2 — the dashboard shell (sidebar, chat, approval modal, task log) runs against mocked Next.js API routes. Sprint 3 — a typed WP tool layer (REST + WP-CLI), encrypted multi-site credentials, and approval-gated tools the agent reaches via natural language.
- **Two approval gates, both deliberate (until Sprint 4):** the frontend approval modal is a UI mock; the backend write tools enforce `approved=True` in code. Sprint 4 replaces both with one real LangGraph interrupt that pauses the orchestration graph and resumes from the dashboard. The Elementor JSON skill and pgvector recall remain target architecture in [project-overview.md](project-overview.md).
- **Version drift:** The overview describes "Next.js 14," but `package.json` pins `16.2.9`. Follow the installed version and its bundled docs.
- **Deps reconciled:** All backend dependencies (including `langgraph` and `anthropic`) now live in `pyproject.toml` / `uv.lock`; there is no separate `requirements.txt`.
