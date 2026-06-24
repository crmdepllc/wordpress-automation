# Project Structure

This document describes the layout of the **WordPress Automation** repository — an AI agent system that builds and manages WordPress/Elementor sites from natural-language instructions. For the intended end-state architecture and the role each technology plays, see [project-overview.md](project-overview.md).

> **Current state:** Sprint 1 (repo setup & architecture spike) is complete. The backend exposes a FastAPI app with a single LangGraph "ping" node that calls Claude; the frontend has a minimal page that drives that node end-to-end; the whole stack boots via Docker Compose. Items marked _(planned)_ come from the overview but are not yet implemented.

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
| `backend` | `./backend` | 8000 | FastAPI + LangGraph agent |
| `frontend` | `./frontend` | 3000 | Next.js dashboard |

Secrets are supplied via `backend/.env` (copy from `backend/.env.example`); the Anthropic API key is never hardcoded. The `wp-init` script lives inline in `docker-compose.yml` as a Compose `config`.

## Backend (`backend/`)

FastAPI server that receives requests from the frontend and routes them into the LangGraph agent, which orchestrates Claude and WordPress tooling.

```
backend/
├── .python-version        # Pins Python 3.14
├── pyproject.toml         # Project metadata + dependencies (uv/PEP 621)
├── uv.lock                # Locked dependency graph (uv)
├── Dockerfile             # Backend image (uv-based, Python 3.14)
├── .dockerignore          # Excludes .venv, caches, .env from the image
├── .env.example           # Env template (copy to .env; holds ANTHROPIC_API_KEY)
├── README.md              # (empty)
├── main.py                # Local launcher — runs uvicorn against app.main:app
└── app/
    ├── __init__.py
    ├── main.py            # FastAPI app: CORS + router mount
    ├── config.py          # pydantic-settings Settings (secrets via env/.env)
    ├── api/
    │   ├── __init__.py
    │   └── routes.py      # /health and POST /api/ping
    └── agent/
        ├── __init__.py
        └── graph.py       # LangGraph "ping" node — calls Claude, returns text
```

- **Package manager:** [`uv`](https://github.com/astral-sh/uv) (`uv.lock`, `pyproject.toml`), Python `>=3.14`.
- **Dependencies:** all declared in `pyproject.toml` — `fastapi[standard]`, `langgraph`, `langgraph-checkpoint-postgres`, `anthropic`, `langchain-anthropic`, `sqlalchemy`/`asyncpg`/`psycopg`/`alembic`/`pgvector`, `redis`/`celery`, `fabric`/`paramiko`, `httpx`, `cryptography`, `pydantic-settings`.
- **Entry point:** [backend/app/main.py](backend/app/main.py) — FastAPI app with CORS and the API router. [backend/main.py](backend/main.py) is a thin uvicorn launcher for local `python main.py`.
- **Agent:** [backend/app/agent/graph.py](backend/app/agent/graph.py) holds the single-node LangGraph (`ping`) that calls Claude via `langchain-anthropic` using the fast model, per the AGENTS.md model-routing rule. This is the Sprint 1 spike — no WordPress tooling or approval gate yet.
- **Config / secrets:** [backend/app/config.py](backend/app/config.py) reads all settings (API key, model names, DB/Redis URLs, CORS) from the environment / `.env`. Nothing is hardcoded.
- **Planned components** _(per overview, not yet present)_: WP skill nodes, orchestration graph + approval gate, PostgreSQL/pgvector persistence wiring, Redis/Celery job queue, WP REST API & WP-CLI/SSH (Fabric/Paramiko) integration.

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
    │   ├── layout.tsx     # Root layout — Geist fonts, global CSS
    │   ├── page.tsx       # Ping UI — posts a prompt to /api/ping, shows the reply
    │   ├── globals.css    # Tailwind import + design-token CSS variables
    │   └── favicon.ico
    ├── components/
    │   └── ui/
    │       └── button.tsx # shadcn Button (Base UI + CVA)
    └── lib/
        └── utils.ts       # cn() class-merge helper
```

- **Framework:** Next.js `16.2.9` (App Router), React `19.2.4`. _Note: the overview refers to "Next.js 14"; the installed version is 16.x._
- **Package manager:** `npm` (`package-lock.json`).
- **Styling:** Tailwind CSS v4 via `@tailwindcss/postcss`, with theme variables in [globals.css](frontend/src/app/globals.css).
- **State / data:** Zustand `^5` (in-memory UI state) and TanStack Query `^5` (server/data fetching) are installed but not yet wired in.
- **AI streaming:** Vercel AI SDK (`ai` `^6`) installed; not yet used.
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

- **Sprint 1 complete:** The end-to-end path (frontend → FastAPI → LangGraph → Claude → back) works. Everything beyond the ping spike (WP tooling, approval gate, persistence) is still the target architecture in [project-overview.md](project-overview.md), not yet built.
- **Version drift:** The overview describes "Next.js 14," but `package.json` pins `16.2.9`. Follow the installed version and its bundled docs.
- **Deps reconciled:** All backend dependencies (including `langgraph` and `anthropic`) now live in `pyproject.toml` / `uv.lock`; there is no separate `requirements.txt`.
