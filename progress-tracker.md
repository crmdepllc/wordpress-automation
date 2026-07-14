# Progress Tracker

Update this file whenever the current phase, active feature, or implementation state changes.


# Sprint plan — agentic WordPress automation platform

This breaks the project from project-overview.md into 10 sequential sprints. Each sprint has a goal, a task list, and a concrete deliverable that marks it done. Sprints are ordered by dependency — don't start a later sprint before the previous one's deliverable is met.

## Current Phase
- Sprint 9 (Security hardening) — next up

## Current Goal
- Sprints 1–8 — ✅ complete; Sprint 9 ready to start

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
- The ping node uses the fast model (`claude-haiku-4-5`) per the AGENTS.md motdel-routing rule — a narrow single-shot call, not orchestrator reasoning.
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

## Sprint 4 — Orchestration graph & approval gate — ✅ COMPLETE

**Phase:** Build

**Goal:** A real orchestrator that plans multi-step tasks and pauses for human approval before writing — replacing the mocked approval flow from Sprint 2 with the real thing.

**Tasks**
- [x] Design the LangGraph state machine: plan → approve → execute → report
- [x] Implement the approval checkpoint as a graph interrupt, resumable from the frontend
- [x] Add task persistence in Postgres so a paused task survives a server restart
- [x] Add Celery + Redis for async/long-running task execution
- [x] Set up LangSmith tracing for every graph run
- [x] Connect the Sprint 2 dashboard to the real interrupt/resume flow in place of the mock

**Deliverable:** A multi-step task (e.g. "install plugin, then create a page") pauses correctly in the real UI and resumes only after approval. — **Met** (unit + HTTP-contract verified; full live run needs the Docker stack + an API key — see notes).

**Architecture decisions (via /architect)**
- **FE↔BE bridge = Next routes proxy to FastAPI.** `/api/chat` starts a real task; `/api/tasks/[id]/resume` pipes the exec stream. Python stays free of the AI-SDK wire format; the Sprint 2 frontend (useChat + data-plan + task store) is reused, not rewritten.
- **Celery = scaffold + inline demo path.** Worker + compose service + `execute_task` exist; the deliverable runs inline so it streams live and is testable here. Celery is ready for genuinely long jobs.
- **Checkpointer = Postgres in app, Memory in tests.** App uses `AsyncPostgresSaver` (thread_id = task_id → survives restart); unit tests use `MemorySaver`; the restart claim is a gated `@integration` test.
- **Chat UX = keep useChat + data-plan.** The plan now comes from the graph interrupt instead of a mock.

**Notes / what shipped**
- `app/agent/orchestrator/`: `state.py`, `planner.py` (NL → ordered tool calls), `graph.py` (`plan → approve[interrupt] → execute → report`), `checkpointer.py`, `manager.py` (start→interrupt, resume+stream), `tasks_service.py`. Routes: `/api/tasks`, `/api/tasks/{id}`, `/api/tasks/{id}/resume` (ndjson stream). Lifespan opens the Postgres checkpointer (falls back to in-memory if Postgres is down so the app still boots).
- `app/worker/` (Celery app + `execute_task`); new `worker` compose service. `tasks` table + Alembic `0002`. LangSmith enabled when `LANGSMITH_API_KEY` is set.
- Frontend rewired: `/api/chat` + a new `/api/tasks/[id]/resume` proxy; `task-store.ts` `resumeTask()` replaces the mock `runExecution`; the old `/api/execute` mock deleted; approval modal drives real approve/reject.
- **The approval invariant is now enforced by the graph:** only `Command(resume="approve")` reaches the execute node → `run_approved`. A reject makes zero tool calls (tested).
- **Tests: 38 passed, 4 skipped** (integration). Frontend `next build` clean. Alembic head `0002`.
- **Not verified live:** the full browser→FastAPI→graph→Claude round trip needs Docker (Postgres/Redis/WP) up and `ANTHROPIC_API_KEY` set; planning calls Claude. The graph/manager/route logic is verified with `MemorySaver`, a mocked planner, and a `TestClient`; persistence-across-restart has a gated integration test.
- Follow-up: a real site selector (currently a single `NEXT_PUBLIC_DEFAULT_SITE` slug); Celery is scaffolded but the demo path is inline.

---

## Sprint 5 — Elementor JSON generation skill — ✅ COMPLETE

**Phase:** Integration

**Goal:** The agent can generate a working Elementor page layout from a plain-language brief. This is the highest-risk sprint — budget extra time and don't compress it to match the others.

**Tasks**
- [~] Hand-build 10–15 real Elementor pages / export their _elementor_data — **partial:** seeded 5 documented section templates (hero/features/pricing/contact/footer) + a loader; genuine editor exports are a documented, integration-gated follow-up (no live Elementor in this env).
- [x] Build the skill: brief → Claude → validate → write via REST — done as **constrained IR → deterministic builder** (Claude fills a PageSpec; code assembles the JSON) per rule #3.
- [x] Post-write step: `wp elementor flush-css` via WP-CLI after every layout write (auto-run inside the tool).
- [x] JSON validator catching malformed structures before writing (structural + semantic).

**Deliverable:** Agent generates a 3–4 section landing page that renders correctly in Elementor without manual fixes, for 5+ test briefs. — **Met offline** (5 brief evals produce valid pages); **true in-editor render is gated** on the live stack (see notes).

**Architecture decisions (via /architect)**
- **Generation = constrained IR → deterministic builder.** Claude fills a small validated `PageSpec` (sections from a catalog + content slots); `builder.py` compiles it into `_elementor_data` from the real example templates, regenerating ids. The fragile JSON is assembled by tested code, never hallucinated — honors AGENTS.md rule #3.
- **Example library = seed 5 documented sections + loader.** Marked reference scaffolds; genuine exports + the render check are integration-gated.
- **Evals = structural now + gated render eval.** 5+ briefs asserted offline (valid schema, sections present, ids unique); a `@integration` eval does the real write when the stack is up.
- **Graph integration = new gated tool with auto flush-css.** `wp_create_elementor_page` is a planner-selectable write tool; the write never happens without approval and never happens if validation fails.

**Notes / what shipped**
- `app/agent/skills/elementor/`: `schema.py` (IR), `library.py`, `builder.py`, `validator.py`, `generator.py`, `skill.py`, `examples/` (5 templates + README). REST `create_elementor_page` writes the `_elementor_data` meta. Tool added to `WP_TOOLS`/`WRITE_TOOLS` (12 tools now).
- **Tests: 66 passed, 5 skipped.** Builder property tests (every section builds valid, unique ids, grid cloning), validator tests (catches missing ids/bad nesting/dup ids/column sums), 5 brief evals through the real pipeline, tool gating + write-path, + a gated live-render eval.
- **Known dependency / caveat:** persisting `_elementor_data` over REST requires the companion WP plugin to register that meta with `show_in_rest`; without it WordPress drops the meta and the page renders blank. This is called out in the REST method and is exactly what the gated render eval checks. **True in-Elementor rendering is unverified here** (no live Elementor/API key); offline we verify structural validity + section coverage.
- Follow-up: replace the seeded scaffolds with genuine editor exports; add more section types (gallery, testimonials); ship the companion plugin's meta registration.

---

## Sprint 6 — Content, SEO & theming skills — ✅ COMPLETE

**Phase:** Integration

**Goal:** Round out the skill set beyond page layout — the things that make a site feel finished.

**Tasks**
- [x] Content generation skill: draft posts, assign categories/tags (find-or-create), schedule via REST API
- [x] SEO skill: generate meta titles/descriptions + JSON-LD schema; Yoast/RankMath meta keys (provider-selectable)
- [x] Theme customizer skill: colors, fonts, footer via WP-CLI theme mods + best-effort Elementor global kit
- [x] Plugin management skill: search + configure (WP-CLI) on top of existing install/activate + a recommend catalog

**Deliverable:** Agent can take a site from blank install to a themed, SEO-configured, content-populated state end-to-end. — **Met at the skill level** (each skill works and is individually evaluated); the single-brief *composite* run is Sprint 7's job, and true live application is gated (see notes).

**Architecture decisions (via /architect)**
- **Write channels:** SEO → REST post-meta (documented `show_in_rest` dependency); theming → WP-CLI `theme mod`/`option` + Elementor kit. Content → REST. Each stays on its rule-correct channel.
- **Scope:** all four skills at pragmatic depth; each gets evals.
- **SEO:** Yoast default, RankMath mapping selectable; Claude writes title/description, code builds JSON-LD by schema type.
- **Terms:** ensure-by-name (find-or-create) — the agent works in human names; the client resolves ids.

**Notes / what shipped**
- `app/agent/skills/`: `content/` (PostDraft generator), `seo/` (providers map + generator + JSON-LD), `theme/` (ThemeSpec generator + WP-CLI applier), `plugins/` (recommend catalog). REST client gained `ensure_category`/`ensure_tag`, scheduling fields on `ContentCreate`, and `update_content_meta`; WP-CLI gained `search_plugin`/`set_option`/`set_theme_mod`/`get|update_post_meta`.
- 5 new tools: `wp_publish_post`, `wp_apply_seo`, `wp_apply_theme` (gated writes), `wp_configure_plugin` (gated), `wp_search_plugins` (read). **17 tools total.**
- **Tests: 89 passed, 7 skipped.** REST term find-or-create + scheduling payload, SEO provider mapping + JSON-LD + `seo_to_meta`, theme applier (mods + Elementor kit merge), content/SEO/theme generators (LLM mocked), all-tool gating, applied paths, + a gated live integration eval.
- **Caveats (same shape as Sprint 5):** Yoast/RankMath meta over REST needs the companion plugin's meta registration; theme mods assume generic Customizer keys (theme-specific keys vary); Elementor kit color merge is best-effort. **No live application verified here** (no WP/API key) — the gated `test_sprint6_live.py` covers it when the stack is up.
- Follow-up: theme-specific Customizer key mapping; richer plugin configuration; wire the composite "blank → finished" run in Sprint 7.

---

## Sprint 7 — Multi-step task decomposition — ✅ COMPLETE

**Phase:** Build

**Goal:** Handle a full brief ("build me a 5-page site") by decomposing it into an ordered task graph automatically.

**Tasks**
- [x] Build the orchestrator-level planning step: brief → ordered list of skill invocations with dependencies
- [x] Handle dependency ordering (theme before content, pages before menu assembly)
- [x] Add a rollback/snapshot mechanism before each major write (WP DB export beforehand)
- [x] Add partial-failure handling: if step 3 of 7 fails, surface it clearly rather than silently continuing

**Deliverable:** A single brief produces a multi-page site with menu, theme, and SEO applied in correct order, unattended after one approval. — **Met** (unit-verified end to end; live multi-page run needs the Docker stack + an API key — see notes).

**Architecture decisions (via /architect)**
- **Dependency source = deterministic category table, not LLM-authored.** The LLM still proposes steps via tool calls (unchanged); code tags each step with a `category` (plugin/theme/page/content/seo/menu) and computes `depends_on` from a fixed precedence table (`plugin → theme → page → content → seo → menu`), then topologically sorts. Mirrors the constrained-IR pattern from the Elementor skill — the model never hand-authors a graph structure that could reference invalid ids or cycle.
- **Cross-step refs = `"$ref:step-id:path"` strings, resolved at execution.** A step that targets content created earlier in the same plan (SEO on a page just created, a menu collecting new pages) uses a `$ref` string instead of a guessed id; `execute_node` resolves it against the referencing step's real result immediately before invoking the tool. Tool schemas widen the relevant id args to `int | str` so the ref string passes validation; gated write tools check `approved` before ever touching the value, so unresolved refs are inert during planning/preview.
- **Rollback = one snapshot, no auto-restore.** A single `wp db export` runs once, right after approval and before the first write (not per-step) — halting on first failure already bounds the blast radius, so one restore point covers it. Restoring it is left to a human (`wp db import`); the agent never runs a second unattended destructive DB operation after a failure. A snapshot failure is logged and surfaced but does not block already-approved writes.
- **Failure mode = halt immediately, mark the rest skipped.** The first failed step stops execution; every remaining step (whether or not it depended on the failure) is reported `skipped`, never silently attempted. The final report's `outcome` is `"failed"` (not `"completed"`) whenever anything failed.
- **Menu assembly built for real.** `wp_assemble_menu` creates a nav menu via the existing `create_menu` REST method and attaches pages as menu items via a new `create_menu_item` REST wrapper (`POST /menu-items`) — needed for the deliverable to be literally true, not just illustrative.

**Notes / what shipped**
- `app/agent/orchestrator/state.py`: `Category`/`CATEGORY_PRECEDENCE`/`category_for_tool()`; `PlannedStep.category` + `PlannedStep.depends_on`; `OrchestratorState.snapshot`; `ExecEvent.status` gained `"skipped"`.
- `app/agent/orchestrator/planner.py`: new `_decompose()` — tags categories, computes `depends_on` from precedence + any `$ref` tokens found in a step's args, topologically orders (Kahn's algorithm, stable on emission order). System prompt documents the `$ref:step-id:path` convention.
- `app/agent/orchestrator/graph.py`: new `snapshot` node between `approve` and `execute` (skips itself when the plan has no writes; failures are caught and non-fatal); `resolve_refs()` substitutes `$ref` tokens from prior steps' real results; `execute_node` now halts on the first failed step and marks the remainder `skipped`; `report_node` adds `skipped` to the count and sets `outcome: "failed"` when anything failed.
- `app/wp/wpcli.py`: `WpCli.export_db(filename)` (`wp db export`) — the snapshot file stays on the WP-CLI target's own filesystem, referenced by name in the report, never downloaded into our infrastructure.
- `app/wp/rest_client.py` / `schemas.py`: `create_menu_item()` (`MenuItemEntry`).
- `app/agent/tools/wp_tools.py`: new gated `wp_assemble_menu` tool (create menu + attach pages, fetching each page's real title); `wp_apply_seo.target_id` widened to `int | str` to accept `$ref` strings. **18 tools total** (13 gated writes).
- **Tests: 102 passed, 4 skipped** (existing count grows to reflect new coverage — decompose ordering + `$ref` dependency + menu-depends-on-pages/content in `test_planner.py`; snapshot taken/skipped/non-fatal-failure + halt-on-failure + skip-marking in `test_orchestrator_graph.py`; `wp_assemble_menu` gating/applied/resolved-ref-input in `test_tools.py`; `export_db` args in `test_wpcli.py`; `create_menu_item` payload in `test_rest_client.py`). One unrelated pre-existing failure (`test_local_docker_executor_command`) reproduces identically on `main` before this sprint's changes — a local Docker-environment mismatch, not a regression.
- **Not verified live:** a real multi-page run (pages → theme → content → SEO → menu, with `$ref`-linked ids resolving against real WP responses) needs the Docker stack + an Anthropic key. Unit tests cover the decomposition, ref-resolution, snapshot, and halt/skip logic with the DB/WP-CLI/REST layers mocked.
- Follow-up: the eval suite (Sprint 8) should add at least one golden "full brief → multi-page site" scenario exercising the real chain end-to-end against the sandboxed WP instance.

---

## Sprint 8 — Eval suite & quality scoring — ✅ COMPLETE

**Phase:** Hardening

**Goal:** Confidence that each skill works reliably, with a repeatable way to catch regressions.

**Tasks**
- [x] Build a golden dataset: 20+ real-world WP task scenarios across all skills
- [x] Automate eval runs against the sandboxed Docker WP instance, scored for correctness
- [x] Add Playwright visual regression: screenshot agent-generated pages, flag visual breaks
- [x] Wire evals into GitHub Actions — every PR touching a skill must pass its eval set

**Deliverable:** CI blocks any PR that regresses a skill's eval score; team has a quality dashboard. — **Met** (offline scored gate is real and enforced in CI; the live Docker+real-Claude scored run and Playwright visual regression are built but intentionally gated/non-blocking — see notes).

**Architecture decisions (via /architect)**
- **CI gate = offline only.** The blocking `pull_request` check runs the deterministic, mocked-LLM/mocked-WP-CLI eval set (no Docker, no API key, seconds not minutes) — extending the offline-eval pattern Sprints 5–6 already established. The live Docker+real-Claude+Playwright run is a separate `workflow_dispatch`/weekly workflow, **not** a required status check, so a paid API key and Docker flakiness never sit in the way of merging.
- **Scoring = weighted checklist, not pass/fail.** Every scenario runs a small list of weighted assertions (`app/evals/scoring.py`) and scores 0–100; a skill's score is the average of its scenarios' scores. A skill that starts failing one minor check registers as a partial regression, not an invisible pass.
- **Regression = fixed per-skill threshold**, committed in `app/evals/thresholds.py` — not a ratcheting baseline file, so improving a score never requires touching a baseline as part of an unrelated PR.
- **One scoring engine, two callers.** `scripts/run_evals.py` (the CI gate + report generator) and `tests/test_evals.py` (the local `pytest` dev loop) both call the same `app/evals/runner.py` — no duplicated scoring logic to drift out of sync.
- **Quality dashboard = generated CI report, not a new frontend page.** Every run writes `eval-report.md` (posted to the GitHub Actions job summary) and `eval-report.json` (uploaded as a build artifact) — no new DB table, API route, or dashboard UI this sprint.
- **Playwright ships even though it's expected red here.** The harness (config + spec + CI wiring) is real, but per the Sprint 5/6 caveat, `_elementor_data` only persists over REST once the companion WP plugin registers it with `show_in_rest` — without it the target page renders blank. The spec documents this inline; it runs only in the non-blocking live workflow.

**Notes / what shipped**
- `app/evals/`: `scoring.py` (`CheckResult`/`ScenarioResult`/`Scenario`/`SkillReport`), `thresholds.py` (per-skill floors: 90 for elementor/content/seo/orchestrator, 85 for theme/plugins), `runner.py` (`run_skill`/`run_all`), `report.py` (markdown + JSON rendering, ASCII status markers — no emoji, so it prints cleanly on a plain Windows console too), `scenarios/` — one file per skill: `elementor.py` (5, relocated from the old `test_elementor_skill.py` SCENARIOS), `content.py` (4), `seo.py` (4), `theme.py` (3), `plugins.py` (3), `orchestrator.py` (4, new — exercises Sprint 7's `planner._decompose` directly: category precedence, `$ref` dependency capture, menu-depends-on-pages/content). **23 scenarios total.**
- `backend/scripts/run_evals.py`: the CLI entry — runs every scenario, writes `eval-out/eval-report.{md,json}`, prints the markdown, exits 1 on any regression.
- `backend/tests/test_evals.py`: pytest wrapper over the same runner (regression gate, scenario-count sanity checks, plus unit tests for the scoring/report primitives themselves). `test_elementor_skill.py` trimmed to its non-scenario edge-case tests, with the 5-brief golden set relocated to `app/evals/scenarios/elementor.py`.
- `.github/workflows/ci.yml` (new — **first CI in this repo**): path-filtered on `pull_request` to `backend/app/**`/`backend/tests/**`/etc.; runs `pytest -m "not integration"` (the full non-integration suite, so an ordinary broken unit test blocks a PR too, not just eval-score regressions) then `scripts/run_evals.py`; publishes the report to the job summary and as an artifact. **Required/blocking.**
- `.github/workflows/eval-live.yml` (new): `workflow_dispatch` + weekly schedule; brings up the Docker Compose sandbox, runs the `@pytest.mark.integration` suite against real WP + a real Claude key (`ANTHROPIC_API_KEY` secret), then the new Playwright suite. **Not required/blocking.**
- `frontend/`: `@playwright/test` added; `playwright.config.ts` (points at `WP_BASE_URL`, the WP sandbox — not the Next app); `tests-visual/elementor-page.spec.ts` (`toHaveScreenshot` diff against a committed baseline, `WP_ELEMENTOR_PAGE_SLUG` selects the target page). No baseline image is committed yet — there's no live page to screenshot in this environment; the harness is mechanically verified (installs, runs, correctly reports "no snapshot yet") but a real baseline is a live-environment follow-up.
- **Tests: 105 passed, 4 skipped** (backend). One unrelated pre-existing failure (`test_local_docker_executor_command`, a local Docker-environment mismatch) persists unchanged from Sprint 7 — not a regression from this sprint. Frontend `tsc --noEmit` clean with the new Playwright files included.
- Follow-up: once the companion WP plugin (Sprints 5/6's documented dependency) ships, run `eval-live.yml` once to capture the first real Playwright baseline; consider a persisted eval-history dashboard in the frontend if the team wants trend lines beyond per-run reports (explicitly deferred this sprint — see architecture decisions).

---

## Companion WP plugin + richer Elementor templates — ✅ COMPLETE (post-Sprint 8 fix)

**Phase:** Hardening (unscheduled — user-reported bug, fixed before starting Sprint 9)

**Goal:** Close the "companion WP plugin" gap that had been open and deferred since Sprint 5, and make generated Elementor pages meaningfully richer, per direct user feedback: *"pages are too simple / CSS is not loading."*

**Tasks**
- [x] Build the companion WP plugin (mu-plugin) so `_elementor_data` + SEO meta actually persist over REST
- [x] Expand the Elementor section library: richer widgets in the existing 5 sections, 4 new section types
- [x] Verify live against the real Docker sandbox (not left as another "not verified live" caveat)

**Deliverable:** A brief produces a real, styled, multi-section Elementor page on a live site — confirmed by actually looking at it, not just by structural validation. — **Met.**

**Architecture decisions (via /architect)**
- **Plugin = mu-plugin, explicit meta-key allowlist.** `wp-plugin/wpa-companion/wpa-companion.php` registers exactly the 7 protected meta keys the codebase writes (3 Elementor, 2 Yoast, 2 RankMath, 1 our own JSON-LD) with `show_in_rest`, each gated by an `edit_post` `auth_callback` — not a wildcard. Auto-loads with zero activation step. Delivered via existing channels only: Docker bind-mount for dev, Fabric/Paramiko file upload for real sites (per AGENTS.md's WordPress integration rules) — no new channel invented.
- **Richness = both deeper existing sections and new non-photo types.** hero/features/pricing/contact/footer gained background colors, icon-box/icon-list/testimonial-style widgets, and more slots; 4 new section types (testimonials, stats, faq, cta_banner) were chosen specifically to avoid needing real photos (no image-sourcing capability exists yet) — gallery/team/image-split are explicitly deferred.
- **FAQ needed a new `"stack"` builder layout** (clone one widget prototype N times into a single column, vs. `"grid"`'s N-columns-side-by-side) — the only structural change to `builder.py`; `validator.py` needed no changes.
- **Verify live, not gated.** Since the Docker sandbox was actually running with a real Elementor install, this pass wrote real pages via the real REST client and looked at the actual rendered output (Playwright screenshots) instead of leaving persistence/rendering as an unverified caveat like Sprints 5/6/8 had to.

**Notes / what shipped — and two real bugs live verification caught that offline/structural checks could not**
- `wp-plugin/wpa-companion/wpa-companion.php` (new) + `wp-plugin/README.md`; bind-mounted into the `wordpress`/`wpcli` Docker services. **This alone did not fully fix the user's report** — see below.
- `app/agent/skills/elementor/schema.py`: `SectionType` widened from 5 to 9 (`+testimonials, stats, faq, cta_banner`).
- `app/agent/skills/elementor/examples/`: all 5 existing templates enriched (background/heading colors; `features` now uses `icon-box`; `contact` now uses `icon-list`; `pricing` gained a `tagline` slot); 4 new templates added.
- `app/agent/skills/elementor/builder.py`: new `_build_stack()` + dispatch.
- `app/agent/skills/elementor/generator.py`: system prompt now covers icon slots (Font Awesome 6 free-solid classes), the `background_color`/`heading_color` contrast pairing, and loosens section-count guidance from 3–4 to 3–6.
- **Bug #1 (live-verification-only): Elementor's Toggle widget needs a `settings.tabs` repeater array**, not flat `tab_title`/`tab_content` keys. The first live render showed Elementor's own placeholder text ("Toggle #1"/"Toggle #2") instead of our questions — structurally valid JSON, wrong widget-settings shape. Fixed in `faq.json`.
- **Bug #2 (live-verification-only, pre-existing since Sprint 6): `theme/applier.py`'s Elementor-kit color merge wrote `_elementor_page_settings` as a plain JSON *string* via WP-CLI**, but Elementor's `Controls_Stack::sanitize_settings()` requires a real PHP array — WordPress does not auto-decode JSON strings the way it auto-unserializes PHP-serialized data. The mismatch caused an **uncaught PHP `TypeError` fatal on every single frontend page load** once a theme had been applied — a completely blank white page with a 200 status, which is exactly what "CSS is not loading" looks like from the outside. Root-caused via `docker logs` on the live sandbox, not something any offline test could have caught. Fixed by adding `WpCli.update_post_meta(..., as_json=True)` (`--format=json`, which tells WP-CLI to decode-then-properly-serialize), used by `applier.py`'s kit-color step. Both the corrupted live Kit meta and the code were fixed; also pinned with a new assertion in `test_apply_theme_sets_mods_and_kit` and a new `elementor_kit_stored_as_array` eval check.
- Contrast follow-up found in the same live pass: a dark `background_color` with no matching text color made headings unreadable. Added a paired `heading_color` slot (hero/footer/contact/cta_banner) wired to `title_color`/`text_color`, and the generator prompt now instructs pairing them.
- **Live verification performed, end to end, against the actual running sandbox** (not a claim): built a 5-section page (hero/features/testimonials/faq/footer) through the real `generate_elementor_page` → `WordPressRestClient.create_elementor_page` → `wp elementor flush-css` pipeline, confirmed `_elementor_data` persisted (was previously silently dropped), confirmed the page rendered with visible Elementor CSS and all new widget types via a real Playwright screenshot, then re-verified after each bug fix until the page looked correct. Test pages and the throwaway Application Password were cleaned up afterward.
- **Tests: 111 passed, 4 skipped.** Same one unrelated pre-existing `test_local_docker_executor_command` failure (Docker-environment mismatch, reproduces on `main`).
- Follow-up: gallery/team/image+text-split section types need a real image-sourcing capability (stock library or AI image gen + `wp.upload_media`) — deferred. The Playwright baseline in `frontend/tests-visual/` can now be captured for real (the render blocker is fixed) — still not done as part of this pass since it wasn't the reported bug.
- **Addendum:** the new `features` section's icon-box widget introduced its own bug — an icon outside Elementor's bundled Font Awesome 5.15.3 set caused live PHP warnings. Root-caused and fixed with a verified icon allowlist (`app/agent/skills/elementor/icons.py`); full writeup in `issues-list.md`, Issue 7.
- **Addendum 2 — design review against real published pages:** user published 3 real generated pages on `digi.local`; direct inspection (screenshots + rendered CSS, not guessing) found the structural content was actually solid (5–6 sections, real copy, working icons), but two real polish gaps: (a) Elementor buttons had no explicit color and fell back to a clashing default green — fixed with a `button_color` slot reused consistently across a page's buttons; (b) the Sprint 6 theme skill has **zero visible effect** on the Astra theme specifically — confirmed via the live page's own CSS (`--ast-global-color-*`, default system font stack) — Astra stores its palette/typography in its own option schema, not generic `theme_mod` keys. (a) is fixed and live-verified; (b) is a documented, scoped follow-up (needs its own research pass into Astra's real option format, not a guess). Full writeup in `issues-list.md`, Issue 8.

---

## Elementor style-only production-quality upgrade — ✅ COMPLETE (post-Sprint 8 fix)

**Phase:** Hardening (unscheduled — direct user follow-up to the Issue 8 design review, this time with a concrete screenshot of a real production site as the bar to hit)

**Goal:** Close the remaining visual gap between generated pages and a real, professionally-designed site — without any new image-sourcing capability, so purely via richer use of existing Elementor widgets (color, shadow, border-radius, icon-circle badges) and two structural gaps (no heading above a grid, no bio/trust-badge section types).

**Tasks**
- [x] `builder.py`: grid/stack sections can now carry an optional heading/eyebrow/subheading above their repeated items (previously structurally impossible)
- [x] Unify `button_color` → `accent_color`, driving both button backgrounds and icon-circle backgrounds, enforced by eval rather than prompt-only convention
- [x] Card styling (`border_radius`/`box_shadow`/`padding`) on `features`/`testimonials`/`pricing`/`about`/`contact`; icon-circle badges on `features`/`badges`
- [x] Two new section types (`about`, `badges`); `footer` converted to a heading + link-column grid
- [x] Live-verify against the Docker sandbox with the exact brief that motivated the request (a notary-services site)

**Deliverable:** The exact brief that prompted the user's complaint (a mobile/online notary site) produces a real, styled, multi-section page — confirmed by building it through the real pipeline and screenshotting the actual rendered result. — **Met.**

**Architecture decisions (via `/architect`, confirmed with the user before building)**
- **Style-only, no new images.** Photo-based screenshot elements (hero photo, headshot, testimonial avatars, map) stayed explicitly out of scope pending a real image-sourcing capability — everything shipped uses only color/shadow/icon substitutes.
- **New section types kept to exactly two** (`about`, `badges`) plus a `footer` structural upgrade — everything else stayed enrichment-only on the existing 9 types, to avoid catalog bloat.
- **FAQ stayed single-column** — a 2-column variant would have needed a second new `builder.py` layout mode for a purely cosmetic gain.
- **Contact form stayed the icon-list approach** — Elementor's real Form widget has an unverified settings schema; building it from assumption would have violated AGENTS.md rule #3.
- **Grid/stack heading support = a nested-section wrapper**, not a new layout keyword: `section -> column -> [heading widgets..., inner section]`, reusing the fact that `validator.py` already permits a section as a column's child — the real Elementor pattern for title-above-grid layouts.

**Notes / what shipped — and two real bugs live verification caught**
- `app/agent/skills/elementor/schema.py`: `SectionType` widened from 9 to 11 (`+about, badges`).
- `app/agent/skills/elementor/builder.py`: `_build_grid`/`_build_stack` now locate the item prototype one level deeper via a new inner-section convention; `_fill_tokens` gained a `blank_unmatched` flag (see Bug #1 below).
- `app/agent/skills/elementor/examples/`: `hero`/`cta_banner` renamed `button_color`→`accent_color`; `features`/`testimonials`/`pricing`/`stats`/`faq` migrated to the nested wrapper with heading/eyebrow slots; `about.json` and `badges.json` added; `footer.json` converted to a heading + link-column grid; `contact.json` got card styling + `accent_color`-driven icon color.
- `app/agent/skills/elementor/generator.py`: system prompt now covers `accent_color` (buttons + icon circles, one value per page), heading/eyebrow guidance for grid/stack sections, background alternation for visual rhythm, and `about`/`badges` for local-service-type briefs.
- `app/evals/scenarios/elementor.py`: `button_colors_applied` → `accent_color_applied` (now also checks icon-box `primary_color`); added `accent_color_consistent`; added a 6th scenario (a notary/local-service brief exercising `about`/`badges`/the enriched `footer`) — 24 scenarios total across all skills.
- **Bug #1 (live-verification-only): `builder.py`'s per-item token-fill pass was blanking section-level scalar tokens.** A grid item prototype can contain both `{{item.x}}` tokens and a section-scalar token (e.g. `icon-box`'s `primary_color` fed by `{{accent_color}}`). The item-only fill pass replaced *any* unmatched token with `""`, so `{{accent_color}}` was wiped out before the later section-content pass ever ran — confirmed by inspecting the real stored `_elementor_data` (`"primary_color": ""`) and visually via a live screenshot showing Elementor's plain black/white default instead of the page's accent color. Fixed with a `blank_unmatched` flag: the item pass now leaves unmatched tokens untouched; only the final section-content pass blanks genuinely-omitted optional slots. Added a regression test.
- **Bug #2 (live-verification-only): testimonial text unreadable on a dark section background.** `heading_color` was only wired to a section's own heading/subheading widgets, not to the `testimonial` widget's own text controls — so a dark-background testimonials section (which the generator is instructed to use for visual rhythm) rendered its quote/name/role text in Elementor's default dark gray, nearly invisible. Read the real widget source (`elementor/includes/widgets/testimonial.php`) for the actual control names (`content_content_color`, `name_text_color`, `job_text_color`) and wired all three to `heading_color`.
- **Verified live, iteratively, against the real Docker sandbox:** built the exact notary-services brief through the real `wp_create_elementor_page` tool three times (once per bug found), confirmed `_elementor_data` persisted correctly, checked `docker logs` for PHP warnings (none new), and screenshotted the final rendered page with Playwright — accent-colored icon circles, readable testimonial text, card shadows, and section headings above every grid all render correctly. Test pages cleaned up afterward.
- **Tests: 118 passed, 4 skipped.** Same one pre-existing, unrelated `test_local_docker_executor_command` failure (reproduces on `main`).
- Full writeup in `issues-list.md`, Issue 9.
- Follow-up: photo-based sections (real hero/about photography, testimonial avatars, map embed) remain deferred pending an image-sourcing capability — same documented gap as the Sprint 5/6 gallery/team deferral.

---

## Gemini content generation (milestone 1 of 2) — ✅ COMPLETE (post-Sprint 8 fix)

**Phase:** Hardening (unscheduled — user rule: Gemini writes all visible content/images, Claude stays the sole author of page structure/`_elementor_data`; this backend had only Claude/Anthropic wired up)

**Goal:** Route all visible copy generation (blog posts, page section text) through Gemini while Claude keeps deciding page structure. Milestone 1 of 2 — image generation is a separate, larger follow-up (new WP media-upload capability + new Elementor image slots), deliberately out of scope here.

**Tasks**
- [x] Add `google-genai` + `langchain-google-genai` deps; `gemini_api_key`/`gemini_content_model`/`gemini_image_model` settings (`config.py`, `.env.example`)
- [x] `content/generator.py`: swap `ChatAnthropic` → `ChatGoogleGenerativeAI` — blog post generation now Gemini end to end
- [x] `elementor/generator.py`: split single-call generation into `LLMGenerator` (Claude, structure + design slots only) → `LLMCopyGenerator` (Gemini, fills every text slot on the same `PageSpec`)
- [x] `elementor/skill.py`: `generate_elementor_page` runs both passes in sequence before `build_and_validate`; unchanged for callers not passing an explicit `copy_generator`
- [x] New eval scenario exercising the real two-pass split (not a passthrough fake) — 25 scenarios total across all skills
- [x] `pytest -m "not integration"` (117 passed, 1 pre-existing unrelated failure) + `scripts/run_evals.py` (all skills 100/100, no regressions)

**Deliverable:** Every skill that generates visible text (blog posts, page copy) calls Gemini; Claude's role is reduced to structural/design decisions on pages. — **Met.**

**Architecture decisions (via `/architect`, confirmed with the user before building)**
- **Copy split without a schema change:** rather than adding new IR fields, `PageSpec`/`SectionSpec` stayed identical — Claude fills a subset of slots (`DESIGN_SLOTS = {icon, background_color, accent_color, heading_color}`) and leaves every other slot empty; Gemini fills exactly the empty slots the section catalog defines. A merge step (`_merge_design_slots`) re-applies the skeleton's design slots over Gemini's output afterward, so a copy-writing model can never silently change a structural/design decision even if it ignores the prompt.
- **`langchain-google-genai` for text, raw `google-genai` reserved for images** (milestone 2) — text generation mirrors the existing `ChatAnthropic` + `.with_structured_output()` pattern exactly; image generation needs direct control over image bytes that LangChain's Gemini wrapper doesn't offer.
- **Image generation deliberately deferred to milestone 2** — needs new image slots on the `hero`/`about` Elementor templates (live-verified per AGENTS.md rule 3) and a new `agent/skills/images/` module. (Milestone 2 found `WordPressRestClient.upload_media()` already existed from Sprint 3 — the "doesn't exist today" note here was based on an incomplete grep during planning, not an actual gap; see that entry's notes.) Scoped narrower than the full planned gallery/team/image-split section types.

**Notes**
- `test_elementor_skill.py` and `evals/scenarios/elementor.py` needed a `PassthroughCopyGenerator`/`_PassthroughCopyGenerator` fake for existing tests whose fake specs already carry final copy — otherwise the default real Gemini copy generator would try to run without a mock.
- `AGENTS.md` already carried the target-state rule (added the same session, before this gap was found in the actual backend) — this closes the gap between that rule and the code.
- Image generation (milestone 2) not started — `project-structure.md`'s "planned, not built" note for image-sourcing still stands.

---

## Gemini image generation (milestone 2 of 2) — ✅ COMPLETE (post-Sprint 8 fix)

**Phase:** Hardening (unscheduled — continuation of the milestone 1 Gemini rule: images generated by Gemini, uploaded to WP media, Claude decides only whether/roughly-what a section's image should show)

**Goal:** Let Claude mark a `hero`/`about` section as wanting an image (a structural decision, not copy); resolve that into a real Gemini-generated image uploaded to the WP media library, in the same gated write path as the rest of page creation.

**Tasks**
- [x] Correction from milestone-1 planning: `WordPressRestClient.upload_media()` already existed (Sprint 3) — no REST client change needed, milestone scope was smaller than planned
- [x] New `agent/skills/images/` module: `generator.py` (`GeminiImageGenerator`, raw `google-genai` SDK, prompt → PNG bytes) + `resolver.py` (`resolve_images`: `PageSpec` + WP client → `PageSpec` with `image_prompt` resolved to `image_url`/`image_id`)
- [x] `elementor/generator.py`: `image_prompt` added to `DESIGN_SLOTS` (Claude's job — it's a structural decision, never shown on the page) with prompt guidance for both the structural and copy passes
- [x] `hero.json`/`about.json`: optional `image` widget added (`{{image_url}}`/`{{image_id}}` tokens), `image_prompt` added to `scalar_slots`
- [x] `builder.py`: `_finalize_image_widgets` drops an `image` widget left with an empty url (unresolved/omitted prompt) and coerces a filled attachment id to `int`
- [x] `elementor/skill.py` split: `generate_page_spec` (structure + copy, no images — used offline) separated from `build_and_validate`, so `wp_create_elementor_page` can resolve images between the two, post-approval only
- [x] `wp_tools.py`: `wp_create_elementor_page` now opens the WP REST client before generation (needed for image upload), calls `generate_page_spec` → `resolve_images` → `build_and_validate` → write → flush
- [x] New tests: `tests/test_images.py` (generator + resolver unit tests), builder tests for the image-widget drop/keep behavior, an end-to-end tool test with a real (unmocked) `resolve_images`
- [x] New eval scenario module `evals/scenarios/images.py` (2 scenarios), wired into `runner.py`/`thresholds.py` — 27 scenarios total across 7 skills
- [x] `pytest -m "not integration"` (124 passed, 1 pre-existing unrelated failure) + `scripts/run_evals.py` (all 7 skills 100/100, no regressions)
- [x] Live-verified against a real WordPress + Elementor sandbox: uploaded a real PNG via `upload_media`, built a page with both `hero` and `about` image widgets via `build_and_validate` → REST write, fetched the rendered page — both widgets rendered with the correct `wp-image-<id>` class and size variant, no PHP warnings/errors, string→int attachment-id coercion confirmed. Test page/media cleaned up afterward.

**Deliverable:** A page brief where Claude decides an image belongs (e.g. a photographer/agency hero, a notary "about" section) produces a real Gemini-generated image, uploaded to the site's media library, referenced in the built `_elementor_data` — end to end through the same approval gate as every other write. — **Met**, including live verification against a real WordPress + Elementor sandbox.

**Architecture decisions (via `/architect` continuation, confirmed with the user before building)**
- **`image_prompt` is a design slot, not copy** — deciding whether a section wants an image and roughly what it depicts is a structural/page-development decision (Claude's job per AGENTS.md), even though the prompt text itself is never shown on the page. The actual pixels are Gemini's job, one step later.
- **Image resolution only runs inside `wp_create_elementor_page`, post-approval** — both the Gemini image call and the WP media upload are real work (an external API call and a site write), so per AGENTS.md rule 1 neither may happen during planning. The offline `generate_page_spec`/`generate_elementor_page` pipeline (used by tests/evals) never resolves `image_prompt` — an unresolved prompt simply builds without an image widget, never a broken one.
- **Scope kept to `hero`/`about` only** — no new section types (gallery/team/image-split) this pass; confirmed with the user as a narrower, live-verifiable surface over the full planned image-capable catalog.
- **No new agent tool for media upload** — `resolve_images` calls `WordPressRestClient.upload_media()` directly from inside the already-gated tool, the same internal-call pattern `wp_create_elementor_page` already uses for the CSS flush.

**Notes**
- **Live-verified against `docker compose up -d wp-db wordpress wp-init wpcli`** (app DB/Redis/backend/frontend not needed for this check): generated an admin app password via `wp user application-password create`, uploaded a real 1x1 PNG through `WordPressRestClient.upload_media()`, built a two-section (`hero`+`about`) page with both image slots resolved through `build_and_validate` (no LLM calls needed — this validates the JSON shape, not the generation prompts), wrote it via REST, and fetched the live rendered page. Both `<img>` tags carried the correct `wp-image-60` class and per-template size (`size-large` hero, `size-medium_large` about); `docker logs` showed no new PHP warnings/errors (only a pre-existing, unrelated `WP_ENVIRONMENT_TYPE` duplicate-constant warning from the compose config). Test page and media deleted afterward via `wp post delete --force`.
- The milestone-1 progress entry incorrectly said `upload_media()` didn't exist — it did (Sprint 3, `rest_client.py`). Corrected in that entry; caught during milestone 2's research by re-reading the file with a content-mode search instead of a file-match-only search.
- Gemini's actual image-generation call (`GeminiImageGenerator`) was not exercised live this session — no `GEMINI_API_KEY` in this environment. What was verified is the part AGENTS.md rule 3 cares about: the Elementor JSON shape a real WP install accepts. The Gemini API call itself is a standard SDK call against a documented endpoint, lower-risk than hand-authored Elementor JSON, and is covered by `tests/test_images.py`'s unit tests against a faked client.
- **Follow-up (Issue 12, `issues-list.md`):** the first real end-to-end run against a live Gemini key surfaced two things: `.env`'s `GEMINI_IMAGE_MODEL` was misconfigured to a text-only model (fixed → `gemini-2.5-flash-image`), and the account's free tier has zero image-generation quota (`limit: 0` — external, needs billing enabled, not a code fix). Also added graceful degradation: `resolve_images` now catches a failed image (any reason) per-section and builds without it rather than failing the whole page — see `app/agent/skills/images/resolver.py` and the new `images` eval scenario (`image generation failure degrades gracefully`). 28 scenarios total now.

---

## Required theme/plugin stack pre-flight check — ✅ COMPLETE (post-Sprint 8 fix)

**Phase:** Hardening (unscheduled — AGENTS.md's plugin-stack rule, Elementor + Royal Addons + ElementsKit, was documented since the earlier session but never actually implemented anywhere in code; user also added a new requirement — the Astra theme — that wasn't documented at all)

**Goal:** Before generating any Elementor page, verify (and install/activate whatever's missing from) the Astra theme and the three required plugins, so a page is never built assuming a stack that isn't actually there.

**Tasks**
- [x] Confirmed via research that none of this existed: no `plugin list`/`is-active`/`theme list`/`is-active`/theme-install-activate in `WpCli`; no status-check tool; no precondition in `wp_create_elementor_page`; the planner has no "always include this step" mechanism (only step *ordering* is code-enforced, membership is purely LLM-proposed)
- [x] Verified real WordPress.org slugs before writing anything (not guessed): theme `astra`; plugins `royal-elementor-addons`, `elementskit-lite` (its real WP.org name literally is "ElementsKit Elementor Addons – Advanced..." — "Advanced" is part of the free plugin's name, not a paid tier)
- [x] Verified the exact WP-CLI subcommands used (`plugin is-active`/`is-installed`, `theme is-active`/`is-installed`) against `developer.wordpress.org`'s official command reference before implementing — Docker was down, so this replaced live ground-truth-checking for this narrow piece
- [x] `app/wp/wpcli.py`: added `plugin_is_installed`/`plugin_is_active`/`install_theme`/`activate_theme`/`theme_is_installed`/`theme_is_active`
- [x] New `app/agent/skills/stack.py`: `ensure_required_stack` — check-then-act (only installs/activates what's actually missing), Elementor fail-closed (`RequiredStackError`), Astra/Royal Addons/ElementsKit best-effort (logged, page proceeds)
- [x] `wp_tools.py`: `wp_create_elementor_page` runs the stack check right after opening the WP-CLI client, before spec generation; reports per-item status under a new `stack_check` response field
- [x] Tests: `WpCli` unit tests for the 6 new methods, dedicated `tests/test_stack.py` (7 cases), `wp_tools.py` tests for hard-fail/best-effort/partial-setup paths (3 new + fixed one pre-existing test that had never mocked `WpCli` at all)
- [x] New eval scenario module `app/evals/scenarios/stack.py` (4 scenarios) wired into `runner.py`/`thresholds.py` — 32 scenarios total across 8 skills
- [x] `AGENTS.md` updated: Astra added alongside the existing plugin-stack rule, plus the fail-closed/best-effort split documented explicitly
- [x] `pytest -m "not integration"` (138 passed, 1 pre-existing unrelated failure) + `scripts/run_evals.py` (all 8 skills 100/100, no regressions)

**Deliverable:** `wp_create_elementor_page` never generates a page against an unverified stack — Astra + Elementor + Royal Addons + ElementsKit are checked (and fixed if missing) every time, with Elementor treated as non-negotiable and the rest as enhancements. — **Met**, code-complete.

**Architecture decisions (via `/architect`, confirmed with the user before building)**
- **Internal precondition inside `wp_create_elementor_page`, not a planner-injected step.** Matches the existing "mandatory, not user-interesting" pattern (auto CSS-flush, image resolution) rather than building new orchestrator "always-include-this-step" machinery the codebase doesn't have. Tradeoff: the user doesn't see "installing Royal Addons" as its own approval-modal line item — it's covered by the single "create Elementor page" approval, with results surfaced in `stack_check`.
- **Elementor hard-required, Astra/Royal Addons/ElementsKit best-effort** — consistent with the graceful-degradation precedent just set for image generation (Issue 12). Nothing can be built without Elementor; core Elementor widgets still work without the other three.
- **Check-then-act, not always-install** — every item's status is checked first (`is-active`, then `is-installed` only if inactive); install/activate only runs for what's actually missing, so a site that's already fully set up costs 4 cheap status checks per page, not repeated installs.

**Notes**
- **Not live-verified against the Docker sandbox** — Docker was down for the entire second half of this session (the same recurring pattern as Issues 1/3/4/5/11). Confidence is still reasonably high: unlike hand-authored Elementor JSON, these are standard WP-CLI boolean subcommands verified directly against `developer.wordpress.org`'s official reference (not guessed from memory — an earlier draft of `theme_is_active` was in fact wrong, caught before it shipped by checking docs instead of assuming). Live verification against a real sandbox is still a should-do before fully trusting this in production, per the same rule #3 spirit — flagged as a follow-up, not silently skipped.
- Found and fixed a real bug while researching before writing any code: `theme_is_active`'s first draft used `wp theme list --status=active --field=name` (ignoring the `slug` argument entirely) instead of the real `wp theme is-active <slug>` boolean command — caught by checking the official WP-CLI docs rather than trusting the initial implementation.

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