# AGENTS.md

This file gives coding agents (Claude Code, Cursor, etc.) the working rules for this repository. Read this before making any changes.

## Read Before Anything Else

Read in this exact order before any implementation:

1. `project-overview.md` — what the project is, what it does, and why it exists
2. `project-structure.md` — full repo layout and where each piece lives
3. `progress-tracker.md` — current feature status and session history

This file does not repeat that content. It only covers how to work in this codebase correctly.

## What this project is, in one line

An agentic AI platform that automates WordPress site building and maintenance — a LangGraph agent powered by Claude plans and executes WP tasks (pages via Elementor, plugins, SEO, theming) against real WordPress sites, with a human approval gate before any change is applied.

## Stack summary

- **Frontend**: Next.js 16 (App Router), Tailwind CSS, shadcn/ui, Zustand, TanStack Query, Vercel AI SDK
- **Backend**: Python, FastAPI, LangGraph, Anthropic SDK
- **Data**: PostgreSQL, pgvector, Redis + Celery
- **WordPress integration**: WP REST API (Elementor `_elementor_data` JSON), WP-CLI over SSH, Fabric/Paramiko, custom WP companion plugin

Full rationale for each tool lives in `project-overview.md` — don't re-litigate stack choices here unless explicitly asked to.

## Rules That Never Change

1. **Never bypass the human approval gate.** Any agent code path that writes to a live WordPress site (REST API write, WP-CLI command, SSH file edit) must pass through the approval/preview step first. Do not add a "fast path" that skips this, even for "safe" operations, without explicit instruction.
2. **Never commit secrets.** WP site credentials, SSH keys, and API tokens are encrypted at rest in Postgres or held in `.env` — never hardcoded, never logged in plaintext, never written to fixtures or test snapshots.
3. **Treat Elementor JSON as fragile.** The `_elementor_data` schema is undocumented and version-sensitive. Any code that generates or mutates it must be validated against the example library in `agent/skills/elementor/examples/` before being trusted — do not hand-write new Elementor JSON structures from assumption.
4. **Every WP-writing skill needs an eval.** If you add or modify a LangGraph skill node that touches WordPress, add or update a corresponding eval case (see Testing below). No skill ships without at least one passing scenario.
5. **Keep Python (backend) and TypeScript (frontend) cleanly separated at the REST/WebSocket boundary.** Don't reach into backend internals from frontend code or vice versa — go through the documented API.
6. **Any time you add, remove, move, or rename a file or directory, update `project-structure.md` in the same change.** This applies to every file — code, config, scripts, tests, docs, examples. Treat it as part of the change, not a follow-up. A PR that changes the file tree without updating `project-structure.md` is incomplete.
7. **Never use hardcoded hex values or raw Tailwind color classes.** Use the design token system (theme variables / config-defined classes) for all colors — no `#3b82f6` or `bg-blue-500` style one-offs.
8. **Update `progress-tracker.md` after every feature.** This is not optional housekeeping — it's how sessions and agents stay in sync on what's done.

## Available Skills

- `/architect` — before any complex feature. Think before building.
- `/imprint` — after any new UI component. Capture patterns.
- `/review` — before demo or when something feels off.
- `/recover` — when something breaks after one failed correction.
- `/remember save` — when a feature spans multiple sessions.
- `/remember restore` — when returning after a multi-session feature.
- `/interview-me` — before implementation when requirements are unclear. Act as an LLM interviewer: ask targeted questions about project goals, workflows, edge cases, constraints, integrations, users, and success criteria to remove ambiguity and build complete project context before development begins.


## Working with the agent (LangGraph)

- Each WP capability is a **skill node** in the LangGraph graph, not a giant prompt. If a task needs new behavior, prefer adding a new node over expanding an existing one.
- Orchestrator-level reasoning uses the larger Claude model; fast, narrow sub-tasks (formatting, short content generation) should use the smaller/faster model. Don't default everything to the most expensive model call.
- Any new tool exposed to the agent (REST call, SSH command, file write) must be wrapped as an explicit LangGraph tool with a typed schema — no raw, unstructured shell calls from inside a skill.
- Log every tool call and its result. If LangSmith tracing is configured, don't disable it locally without good reason — most agent bugs are debugged through traces, not print statements.

## WordPress integration conventions

- **Content/pages/Elementor data** → WP REST API only.
- **Installs, plugin activation, cache flush (`wp elementor flush-css`), exports/imports** → WP-CLI over SSH only.
- **Theme file edits (`functions.php`, custom widgets)** → Fabric/Paramiko file operations only.
- Don't mix these — e.g. don't shell out to WP-CLI for something the REST API already handles cleanly, and don't write `_elementor_data` by SSH-editing the database directly.
- After any Elementor layout write, trigger a CSS regeneration. A write that skips this step is incomplete even if the API call succeeded.

## Testing

- **Backend**: `pytest`. Run unit tests for tool wrappers and integration tests for skill nodes before opening a PR.
- **Agent evals**: scenario-based tests against a sandboxed WP instance (Docker). If you touch a skill, run its eval set and report pass/fail — don't just run it silently and assume it's fine.
- **Frontend**: Playwright for dashboard flows and visual regression on agent-generated pages.
- Don't mark a task complete if evals are red. Fix or flag, don't skip.

## Before opening a PR

- Run `pytest` (backend) and the relevant Playwright suite (frontend) locally.
- If you changed a skill node, include before/after output from its eval case in the PR description.
- If you changed anything touching Elementor JSON generation, note which example structures in `agent/skills/elementor/examples/` you validated against.
- If this PR added, removed, moved, or renamed any file or directory, `project-structure.md` must be updated in this same PR — don't let it drift out of date.
- Confirm `progress-tracker.md` reflects the feature you just shipped.

## What not to do

- Don't add a new top-level framework or swap a core stack piece (e.g. replacing LangGraph, switching off Postgres) without raising it explicitly — these were deliberate choices tied to the rest of the architecture.
- Don't write directly to the production WordPress database as a shortcut. Every write goes through REST API, WP-CLI, or the file-operations layer, in that order of preference.
- Don't generate Elementor JSON from scratch without consulting the example library first.
- Don't disable the approval gate to "speed up testing" in a way that could leak into a non-test code path.
- Don't use hardcoded hex values or raw Tailwind color classes anywhere in the frontend.