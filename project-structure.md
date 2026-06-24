# Project Structure

This document describes the layout of the **WordPress Automation** repository — an AI agent system that builds and manages WordPress/Elementor sites from natural-language instructions. For the intended end-state architecture and the role each technology plays, see [project-overview.md](project-overview.md).

> **Current state:** The repo is an early scaffold. The frontend is still the default `create-next-app` template and the backend is a stub `main()`. The directory tree and dependencies below reflect what exists today; items marked _(planned)_ come from the overview but are not yet implemented.

## Top-level layout

```
wordpress-automation/
├── AGENTS.md              # Agent guidance (currently empty)
├── CLAUDE.md              # Claude Code instructions — imports AGENTS.md
├── project-overview.md    # Intended architecture & rationale (the "why")
├── project-structure.md   # This file (the "where")
├── backend/               # FastAPI + LangGraph agent server (Python)
└── frontend/              # Next.js dashboard / chat UI (TypeScript)
```

The repo is split into two independently-managed apps: a **Python backend** (`uv`-managed) and a **TypeScript frontend** (`npm`-managed). There is no shared root package manager.

## Backend (`backend/`)

FastAPI server that receives requests from the frontend and routes them into the LangGraph agent, which orchestrates Claude and WordPress tooling.

```
backend/
├── .python-version        # Pins Python 3.14
├── pyproject.toml         # Project metadata + dependencies (uv/PEP 621)
├── requirements.txt       # Extra planned deps: langgraph, anthropic[aiohttp]
├── uv.lock                # Locked dependency graph (uv)
├── README.md              # (empty)
├── main.py                # Entry point — currently a "Hello from backend!" stub
├── .venv/                 # Local virtualenv (not tracked)
└── __pycache__/           # Python bytecode cache
```

- **Package manager:** [`uv`](https://github.com/astral-sh/uv) (`uv.lock`, `pyproject.toml`), Python `>=3.14`.
- **Declared dependency:** `fastapi[standard]>=0.138.0` (in `pyproject.toml`).
- **Planned dependencies:** `langgraph`, `anthropic[aiohttp]` (listed in `requirements.txt`, not yet in `pyproject.toml`).
- **Entry point:** [backend/main.py](backend/main.py) — placeholder `main()`; no FastAPI app or routes defined yet.
- **Planned components** _(per overview, not yet present)_: LangGraph agent graph, Anthropic SDK calls, PostgreSQL + pgvector/Qdrant persistence, Redis/Celery job queue, WP REST API & WP-CLI/SSH (Fabric/Paramiko) integration.

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
├── next-env.d.ts          # Next.js generated types (not tracked)
├── README.md              # Default create-next-app readme
├── public/                # Static assets (next.svg, vercel.svg, file.svg, globe.svg, window.svg)
└── src/
    └── app/               # Next.js App Router
        ├── layout.tsx     # Root layout — Geist fonts, global CSS
        ├── page.tsx       # Home page — default create-next-app template
        ├── globals.css    # Tailwind import + CSS theme variables
        └── favicon.ico
```

- **Framework:** Next.js `16.2.9` (App Router), React `19.2.4`. _Note: the overview refers to "Next.js 14"; the installed version is 16.x._
- **Package manager:** `npm` (`package-lock.json`).
- **Styling:** Tailwind CSS v4 via `@tailwindcss/postcss`, with theme variables in [globals.css](frontend/src/app/globals.css).
- **State / data:** Zustand `^5` (in-memory UI state) and TanStack Query `^5` (server/data fetching) are installed but not yet wired in.
- **AI streaming:** Vercel AI SDK (`ai` `^6`) installed; not yet used.
- **Scripts:** `dev`, `build`, `start` (Next.js) and `lint` (ESLint).
- **Path alias:** `@/*` resolves to `frontend/src/*`.
- **Planned components** _(per overview, not yet present)_: shadcn/ui components, dashboard, chat interface, live preview panel, approval modals.

## Documentation & agent files

| File | Purpose |
|------|---------|
| [project-overview.md](project-overview.md) | Narrative architecture — frontend, backend, and WordPress/Elementor integration layers, and the role of each tool. |
| [project-structure.md](project-structure.md) | This file — directory layout and current vs. planned state. |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Root agent instructions (`CLAUDE.md` imports `AGENTS.md`; both currently empty of content). |
| [frontend/CLAUDE.md](frontend/CLAUDE.md) / [frontend/AGENTS.md](frontend/AGENTS.md) | Frontend-specific note: the installed Next.js has breaking changes vs. older docs — consult `node_modules/next/dist/docs/` before writing code. |

## Notable observations

- **Not yet implemented:** Neither app contains application logic. The backend is a print stub; the frontend is unmodified scaffolding. The architecture in [project-overview.md](project-overview.md) is the target, not the current reality.
- **Version drift:** The overview describes "Next.js 14," but `package.json` pins `16.2.9`. Follow the installed version and its bundled docs (per [frontend/AGENTS.md](frontend/AGENTS.md)).
- **Backend deps split:** Runtime deps live in `pyproject.toml`, but `langgraph`/`anthropic` are only in `requirements.txt` — they need to be reconciled into `pyproject.toml` before the agent layer is built.
