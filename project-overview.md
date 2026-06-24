Here's the complete project overview, pulling together everything we've covered.## What this project actually is

This is an **AI agent platform that automates WordPress site building and maintenance using natural language instructions, with Elementor as the page-building engine**. Instead of a developer manually configuring a theme, building pages in the Elementor editor, writing SEO meta, and installing plugins one by one, you describe what you want — *"build a 5-page portfolio site for a photographer, set up SEO, and use a dark minimal aesthetic"* — and the agent plans the work, executes it against a real WordPress site, and asks for your approval before anything risky or destructive happens.

It's not a chatbot that gives you instructions to follow yourself. It's a system that holds real credentials to a real WP site and does the work directly, the way a junior developer on your team would, while you stay in the loop for anything sensitive.

## How a request actually flows through the system

A user types a request into the **Next.js dashboard**. That request hits the **FastAPI** backend, which hands it to the **LangGraph agent** — the actual decision-making core. LangGraph breaks the request into steps and, at each step, calls **Claude** to reason about what to do: which skill to invoke, what content to generate, what an Elementor layout should contain.

Before anything is written to the live site, the plan passes through a **human approval gate** in the dashboard — you see a diff or preview and confirm it. Once approved, the agent executes against WordPress through three separate channels depending on the task: the **WP REST API** for creating pages and writing Elementor's `_elementor_data` JSON, **WP-CLI over SSH** for things like installing plugins or flushing Elementor's CSS cache, and a **custom WP plugin** for anything that needs a direct hook inside WP Admin itself.

Throughout this, **PostgreSQL** keeps a record of every project and task, **pgvector** lets the agent recall similar past projects, and **Redis** queues longer-running jobs so the dashboard never just hangs waiting on a multi-minute task.

## Tool-by-tool role in plain terms

| Tool | What it's actually doing here |
|---|---|
| **Next.js 14** | The dashboard you open in a browser — chat box, live preview, approval prompts |
| **Tailwind CSS** | Visual styling for that dashboard |
| **shadcn/ui** | The actual UI pieces — modals, command palette, sidebars |
| **Zustand** | Tracks what's happening live on screen right now |
| **TanStack Query** | Fetches and refreshes data from the backend and WP without manual reloads |
| **Vercel AI SDK** | Streams Claude's response into the chat as it's generated |
| **FastAPI** | Receives requests, routes them into the agent, exposes callback endpoints |
| **LangGraph** | The agent's brain — plans steps, routes to skills, pauses for approval |
| **Anthropic SDK / Claude** | Does the actual reasoning and content generation at each step |
| **PostgreSQL** | Stores project records, task history, encrypted WP credentials |
| **pgvector** | Lets the agent recall similar past WP projects for context |
| **Redis + Celery** | Queues long WP tasks so requests don't time out |
| **WP REST API** | Creates pages/posts and writes Elementor's layout JSON directly |
| **WP-CLI over SSH** | Installs plugins, flushes Elementor cache, runs server-level commands |
| **Fabric / Paramiko** | SSH library used for file-level edits like `functions.php` |
| **Custom WP plugin** | Embeds the agent UI in WP Admin and adds endpoints for cache rebuilds after layout changes |

The one architectural detail worth remembering going forward: because Elementor's JSON schema isn't public or stable, the quality of the agent's page-building skill depends entirely on how good a library of real, hand-built Elementor JSON examples you feed it to pattern-match against — that's likely to be one of the more labor-intensive parts of Phase 3.

## Installed libraries and their roles

The dependencies below have been installed against the architecture above. The backend is managed with `uv` (Python 3.14, declared in `backend/pyproject.toml`); the frontend with `npm` (`frontend/package.json`).

### Backend (Python — `uv`)

| Library | Role in this project |
|---|---|
| **fastapi[standard]** | HTTP server that receives dashboard requests, routes them into the agent, and exposes callback endpoints the WP plugin calls back into. The `[standard]` extra bundles Uvicorn and the dev server. |
| **langgraph** | The agent's brain — defines the request flow as a graph (understand → pick skill → call WP tools → pause for approval → report) and manages retries and human-in-the-loop pauses. |
| **langgraph-checkpoint-postgres** | Persists LangGraph agent state/checkpoints in PostgreSQL so a paused task (e.g. waiting on approval) survives restarts and can be resumed. |
| **anthropic** | The Anthropic SDK — direct Claude API access for reasoning and content generation at each graph node. |
| **langchain-anthropic** | Adapter that lets LangGraph nodes call Claude through the LangChain model interface (tool-calling, structured output) instead of raw SDK calls. |
| **sqlalchemy** | ORM / query layer for the persistent data — project records, task history, skill configs, encrypted WP credentials. |
| **asyncpg** | High-performance async PostgreSQL driver used by SQLAlchemy for the app's own async DB access. |
| **psycopg[binary]** | Postgres driver required by `langgraph-checkpoint-postgres`. The `[binary]` extra bundles `libpq`, so no system Postgres client library is needed for local dev. |
| **alembic** | Database schema migrations — versioned, repeatable changes to the PostgreSQL schema as the data model evolves. |
| **pgvector** | Python bindings for the pgvector Postgres extension — stores and queries embeddings of past projects/docs so the agent can recall similar work. |
| **redis** | Client for the Redis broker/result store that backs the job queue. |
| **celery** | Runs long WordPress tasks (multi-minute setups) as background jobs so HTTP requests return immediately instead of timing out. |
| **fabric** | High-level SSH automation — runs WP-CLI commands on the remote server (install plugins, flush Elementor CSS cache, regenerate CSS). |
| **paramiko** | The underlying SSH library (a Fabric dependency) used for direct file-level work such as editing `functions.php`. |
| **httpx** | Async HTTP client used to call the WordPress REST API — creating pages/posts and reading/writing Elementor's `_elementor_data` meta. |
| **cryptography** | Encrypts WordPress credentials at rest before they're stored in PostgreSQL. |
| **pydantic-settings** | Typed, environment-variable-based application configuration (DB URLs, API keys, SSH targets). |

### Frontend (TypeScript — `npm`)

Already present from the initial scaffold: **next** (16.x, App Router), **react** / **react-dom** (19.x), **tailwindcss** (v4), **@tanstack/react-query** (server-state fetching/refresh), **zustand** (live in-memory UI state), and **ai** (Vercel AI SDK — streams Claude's response into the chat).

Added in this pass via `shadcn init`:

| Library | Role in this project |
|---|---|
| **shadcn** (CLI) | Generator that scaffolds UI components directly into `src/components/ui/` (modals, command palette, sidebars) rather than shipping them as a runtime package. Created `components.json`, `src/lib/utils.ts`, and a sample `button.tsx`. |
| **@base-ui/react** | Unstyled, accessible component primitives that shadcn components are built on (this shadcn version uses Base UI in place of Radix). |
| **class-variance-authority** | Defines component style variants (size/intent) in a typed way — the backbone of shadcn component styling. |
| **clsx** + **tailwind-merge** | Conditionally compose and de-duplicate Tailwind class strings (combined in the generated `cn()` helper). |
| **lucide-react** | Icon set used throughout the shadcn components. |
| **tw-animate-css** | Tailwind v4 animation utilities used by shadcn components (e.g. modal/dialog transitions). |

### Not installed (runtime services, not packages)

The **PostgreSQL server** (with the pgvector extension enabled), the **Redis server**, and the **custom WordPress plugin** are infrastructure/services rather than libraries — they're provisioned and deployed separately, not added to a package manifest.