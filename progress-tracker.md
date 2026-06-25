# Progress Tracker

Update this file whenever the current phase, active feature, or implementation state changes.


# Sprint plan — agentic WordPress automation platform

This breaks the project from project-overview.md into 10 sequential sprints. Each sprint has a goal, a task list, and a concrete deliverable that marks it done. Sprints are ordered by dependency — don't start a later sprint before the previous one's deliverable is met.

## Current Phase
- Sprint 4 (Orchestration graph & approval gate) — next up

## Current Goal
- Sprints 1–3 — ✅ complete; Sprint 4 ready to start

---

## Sprint 1 — Repo setup & architecture spike — ✅ COMPLETE

**Phase:** Foundation

**Goal:** A running skeleton — an empty agent loop talking to a test WP site, nothing functional yet.

**Tasks**
- [x] Scaffold monorepo: /frontend (Next.js), /backend (FastAPI + LangGraph), per project-structure.md
- [x] Docker Compose: Postgres (pgvector), Redis, local WP + Elementor instance, FastAPI, Next.js
- [x] Set up Anthropic SDK auth, env config, secrets handling (no hardcoded keys)
- [x] Write a single LangGraph node — "ping" — that calls Claude and returns text, no WP yet

**Deliverable:** Dev environment boots with one command (`docker compose up --build`); agent responds to a test prompt end-to-end through the API. — **Met.**

**Notes**
- LangGraph lives inside the backend (`backend/app/agent/`) per project-structure.md, which defines the backend as the "FastAPI + LangGraph agent server" — not a separate top-level `/agent` package, which would have duplicated the `uv` environment.
- The ping node uses the fast model (`claude-haiku-4-5`) per the AGENTS.md model-routing rule — a narrow single-shot call, not orchestrator reasoning.
- Verified locally: backend imports cleanly, `/health` → ok, `/api/ping` validates input (422 on empty) and routes through the graph to a clear error when `ANTHROPIC_API_KEY` is unset (400). A real Claude round-trip requires the user's key in `backend/.env` (intentionally not committed). Frontend type-checks clean.

---

## Sprint 2 — Dashboard, chat UI & approval UI — ✅ COMPLETE

**Phase:** Foundation

**Goal:** A usable interface shell — type a request, watch it stream, approve or reject a plan. Built early against a minimal/mocked backend so frontend work isn't blocked on later sprints; wired up to real data as those sprints land.

**Tasks**
- [x] Build Next.js dashboard shell with shadcn/ui-style components: sidebar, project list, chat panel
- [x] Wire Vercel AI SDK useChat to a streaming endpoint (mocked `/api/chat`)
- [x] Build the approval modal: shows planned changes/diff, approve/reject buttons
- [x] Zustand store for live task state; TanStack Query for project/site data
- [x] Task log panel showing each tool call and its result, for transparency

**Deliverable:** A non-technical user can type a request, see a plan, approve it, and watch a (mocked) execution stream live. — **Met.**

**Notes**
- Added `@ai-sdk/react` (Vercel AI SDK React bindings) — `ai` v6 ships server stream helpers but not the `useChat` hook. `useChat` posts to `/api/chat`, which streams assistant text plus a typed `data-plan` part; the chat panel surfaces that plan to the approval modal.
- The plan flows through Zustand (`store/task-store.ts`): chat proposes a plan → status `awaiting_approval` → modal Approve calls `runExecution()`, which streams ndjson tool events from `/api/execute` into the live task log → status `completed`. Reject sets `rejected`.
- shadcn-style primitives are hand-built on Base UI + CVA (matching the existing `button.tsx`), design-tokens only — no hardcoded colors.
- **This is a mock.** Per the sequencing notes, Sprint 2's approval flow is a UI mock until Sprint 4 replaces `/api/chat` + `/api/execute` with the real LangGraph interrupt/resume against the FastAPI backend.
- Sprint 1's ping spike is preserved at `/ping`. Verified: `tsc` clean, `next build` clean (8 routes), and all three mock endpoints return correct data at runtime (projects JSON, chat stream w/ plan, execute ndjson log).
- Follow-up: run `/imprint` to capture the new UI component patterns (per AGENTS.md).

---

## Sprint 3 — WP REST API & WP-CLI tool wrappers — ✅ COMPLETE

**Phase:** Build

**Goal:** The agent can read and write to a real WP site through typed tools — no Elementor or skills logic yet.

**Tasks**
- [x] Build WP REST API client: auth via Application Passwords, CRUD for posts/pages/media/menus
- [x] Build WP-CLI wrapper over SSH (Paramiko/Fabric): install, activate, flush-cache commands
- [x] Wrap each as a typed LangGraph tool with explicit input/output schemas
- [x] Write Pytest unit tests for every tool wrapper against the Dockerized WP instance
- [x] Add credential storage in Postgres (encrypted) for multiple WP sites

**Deliverable:** Agent can create a blank WP page and install a plugin via natural language, with passing tests. — **Met** (unit-verified; live demo needs Docker + an App Password — see notes).

**Architecture decisions (via /architect)**
- **WP-CLI transport = pluggable.** One interface, two backends: Fabric/Paramiko SSH for real client sites, `docker exec` into a new persistent `wpcli` compose service for the local sandbox (Apache WP container has no sshd). Chosen per-site via `wpcli_transport`.
- **Tests = unit + gated integration.** Unit tests mock httpx (`respx`) and SSH/subprocess → always green without Docker. Integration tests are marked `@pytest.mark.integration` and self-skip when WP/Docker is down.
- **Approval = code-level gate now.** Real interrupt graph is Sprint 4; here every write tool refuses unless `approved=True`, and `wp_agent.run_approved` is the only path that grants it. `propose()` dry-runs writes to a preview without touching the site.
- **Encryption = Fernet key in env.** `CREDENTIAL_ENCRYPTION_KEY` from settings/.env; `EncryptedString` column encrypts secrets at rest; missing key fails loudly.

**Notes / what shipped**
- `app/wp/`: `rest_client.py` (CRUD posts/pages/media/menus), `wpcli.py` (Ssh + LocalDocker executors, install/activate/flush-css), `credentials.py`, `schemas.py`. `app/crypto.py` + `app/db/` (async engine, `WpSite` model, Alembic migration `0001`). `app/agent/tools/wp_tools.py` (11 typed tools, 7 gated writes) + `app/agent/wp_agent.py`. Routes: `/api/wp/sites`, `/api/wp/plan`, `/api/wp/execute`.
- New persistent `wpcli` service added to `docker-compose.yml`.
- **Tests: 26 passed, 3 skipped** (integration). Alembic migration validated (`alembic history` → head `0001`).
- **Not verified live:** a real REST write against the sandbox needs an Application Password (the default admin login won't authenticate REST writes) and Docker running for WP-CLI. The integration tests cover this and skip until both are present.
- Follow-up: Sprint 4 replaces the two interim approval gates (frontend mock + backend `approved` flag) with one real LangGraph interrupt.

---

## Sprint 4 — Orchestration graph & approval gate — ▶ NEXT UP

**Phase:** Build

**Goal:** A real orchestrator that plans multi-step tasks and pauses for human approval before writing — replacing the mocked approval flow from Sprint 2 with the real thing.

**Tasks**
- Design the LangGraph state machine: plan → select skill → preview → approve → execute → report
- Implement the approval checkpoint as a graph interrupt, resumable from the frontend
- Add task persistence in Postgres so a paused task survives a server restart
- Add Celery + Redis for async/long-running task execution
- Set up LangSmith tracing for every graph run
- Connect the Sprint 2 dashboard to the real interrupt/resume flow in place of the mock

**Deliverable:** A multi-step task (e.g. "install plugin, then create a page") pauses correctly in the real UI and resumes only after approval.

---

## Sprint 5 — Elementor JSON generation skill

**Phase:** Integration

**Goal:** The agent can generate a working Elementor page layout from a plain-language brief. This is the highest-risk sprint — budget extra time and don't compress it to match the others.

**Tasks**
- Hand-build 10–15 real Elementor pages covering common sections (hero, gallery, pricing, contact, footer)
- Export their _elementor_data JSON into an example library for pattern-matching
- Build the skill: brief → Claude generates Elementor JSON → validate against schema → write via REST API
- Add the post-write step: trigger wp elementor flush-css via WP-CLI after every layout write
- Build a JSON-schema validator to catch malformed structures before they're written

**Deliverable:** Agent generates a 3–4 section landing page that renders correctly in Elementor without manual fixes, for 5+ test briefs.

---

## Sprint 6 — Content, SEO & theming skills

**Phase:** Integration

**Goal:** Round out the skill set beyond page layout — the things that make a site feel finished.

**Tasks**
- Content generation skill: draft posts, assign categories/tags, schedule via REST API
- SEO skill: generate meta titles/descriptions, schema markup; integrate with Yoast/RankMath REST endpoints
- Theme customizer skill: colors, fonts, header/footer via WP Customizer API + Elementor global settings
- Plugin management skill: search, install, activate, configure common plugins (forms, caching)

**Deliverable:** Agent can take a site from blank install to a themed, SEO-configured, content-populated state end-to-end.

---

## Sprint 7 — Multi-step task decomposition

**Phase:** Build

**Goal:** Handle a full brief ("build me a 5-page site") by decomposing it into an ordered task graph automatically.

**Tasks**
- Build the orchestrator-level planning step: brief → ordered list of skill invocations with dependencies
- Handle dependency ordering (theme before content, pages before menu assembly)
- Add a rollback/snapshot mechanism before each major write (WP DB export beforehand)
- Add partial-failure handling: if step 3 of 7 fails, surface it clearly rather than silently continuing

**Deliverable:** A single brief produces a multi-page site with menu, theme, and SEO applied in correct order, unattended after one approval.

---

## Sprint 8 — Eval suite & quality scoring

**Phase:** Hardening

**Goal:** Confidence that each skill works reliably, with a repeatable way to catch regressions.

**Tasks**
- Build a golden dataset: 20+ real-world WP task scenarios across all skills
- Automate eval runs against the sandboxed Docker WP instance, scored for correctness
- Add Playwright visual regression: screenshot agent-generated pages, flag visual breaks
- Wire evals into GitHub Actions — every PR touching a skill must pass its eval set

**Deliverable:** CI blocks any PR that regresses a skill's eval score; team has a quality dashboard.

---

## Sprint 9 — Security hardening

**Phase:** Hardening

**Goal:** Close the gaps that matter once this touches real client sites.

**Tasks**
- Audit: agent cannot execute arbitrary PHP/shell beyond the explicit allow-listed WP-CLI commands
- Add rate limiting and per-site cost controls on LLM and API usage
- Review credential storage and rotation; move to Vault if managing 10+ sites
- Add staging-first enforcement: agent always runs against staging before production, configurable per project

**Deliverable:** Internal security review signed off; no direct production writes without a staging pass.

---

## Sprint 10 — Beta launch

**Phase:** Hardening

**Goal:** Prove the system on real work, not test scenarios.

**Tasks**
- Run 3–5 real WP projects through the agent with a human reviewing every approval gate
- Log every failure mode and edge case the eval suite missed; feed back into Sprint 5/6 skills
- Write onboarding docs and a short example-project library for new team members
- Retro: which skills saved the most time, which need another pass

**Deliverable:** 5 real sites shipped using the agent; documented time-savings and known limitations.

---

## Sequencing notes

- **Sprint 2 (dashboard) ships early, against mocked data on purpose.** This unblocks frontend work in parallel with backend sprints, but it means Sprint 2's approval flow is a mock until Sprint 4 wires it to the real LangGraph interrupt — don't treat Sprint 2's "done" as production-ready end to end.
- **Sprint 5 is the bottleneck** (Elementor JSON generation). Everything before it is plumbing; everything after it depends on the agent reliably producing valid Elementor layouts. Don't rush the example library — a flaky page-generation skill poisons every later sprint.
- **Sprint 4 (approval gate) replaces Sprint 2's mock with the real thing.** The interrupt is built into the LangGraph state machine, then reconnected to the dashboard that already exists.
- **Sprint 8 (evals) happens after the skills exist, not before.** Writing eval scenarios against real skill behavior beats guessing at failure modes in advance.
- **Sprint 10 is not "done."** Treat its findings as a backlog for a second iteration, not a wrap-up — it's there to prove (or disprove) that Sprints 5 and 6 hold up outside a Docker sandbox.