# Issues List

Tracks bugs found during development: what broke, which sprint it belongs to, and how it was resolved.

---

## Issue 1 — `POST /api/tasks` returns 400 "Planning failed" when running the backend outside Docker

**Sprint:** Sprint 4 — Orchestration graph & approval gate

**Symptom:**
```
POST /api/tasks HTTP/1.1" 400 Bad Request
```
Preceded by a startup warning:
```
Postgres checkpointer unavailable (failed to resolve host 'postgres': [Errno 11001] getaddrinfo failed); using in-memory checkpointer (paused tasks will NOT survive a restart).
```

**Root cause:**
`backend/.env`'s `DATABASE_URL` was set to `postgresql+asyncpg://wpa:wpa@postgres:5432/wpa` — the hostname `postgres` only resolves inside the Docker Compose network (see `docker-compose.yml`, service name `postgres`). The backend was started directly with `uv run .\main.py` instead of via `docker compose up`, so DNS resolution for `postgres` failed.

The LangGraph checkpointer has an explicit fallback for this (logs a warning, drops to `MemorySaver`) per the Sprint 4 design. However, the plain SQLAlchemy engine used by `get_session()` (for `create_task`/`set_status` against the `tasks` table) has no such fallback. `TaskManager.start()` calls `create_task(session, ...)` first, which fails the same DNS lookup — that exception is caught by the generic `except Exception` in `start_task` (`app/api/task_routes.py`) and returned as `400 Bad Request: "Planning failed: ..."`, which is misleading since planning (the Claude call) never actually ran.

Docker Desktop was also not running at all on the host, so `postgres`/`redis` containers weren't up regardless of hostname.

**Solution:**
1. Changed `backend/.env` `DATABASE_URL` and `REDIS_URL` to point at `localhost` instead of the Compose service names (`postgres` → `localhost`, `redis` → `localhost`), since `docker-compose.yml` publishes both ports to the host (`5432:5432`, `6379:6379`). This lets the backend run locally via `uv run .\main.py` against containers still managed by Compose.
2. Requires Docker Desktop to be running, with at least `postgres` and `redis` started: `docker compose up -d postgres redis`.
3. Not changed but worth noting as a follow-up: the generic `except Exception` → `400 "Planning failed"` in `start_task` conflates DB errors with actual LLM planning errors. A future pass could distinguish infra errors (503) from planning/model errors (400) for clearer diagnostics.

**Status:** Resolved (config fix). Follow-up (error-classification clarity) not implemented — flagged for later.

---

## Issue 2 — Live Anthropic API key committed to `backend/.env.example`

**Sprint:** N/A (cross-cutting — violates AGENTS.md rule #2, "Never commit secrets")

**Symptom:** `backend/.env.example` (a file tracked in git, meant to hold only blank placeholders) had `ANTHROPIC_API_KEY` set to a real, live-looking key instead of empty. The same key was also present in `backend/.env` (correctly gitignored, but still a live secret that had been pasted into a tracked file).

**Root cause:** The real key appears to have been pasted into `.env.example` instead of (or in addition to) `.env`, likely by accident while setting up local credentials.

**Solution:**
1. Reverted `backend/.env.example`'s `ANTHROPIC_API_KEY` back to blank (`ANTHROPIC_API_KEY=`).
2. `backend/.env` itself is correctly gitignored (verified via `.gitignore`), so the key was not committed to git history.
3. **Action required from the user:** rotate/revoke this Anthropic API key immediately, since it was exposed in a working-tree file and in tool/session logs, even though it was never pushed to a remote.

**Status:** File-level fix applied. Key rotation is a manual step the user must still do.

---

## Issue 3 — `password authentication failed for user "wpa"` after pointing `DATABASE_URL` at `localhost`

**Sprint:** Sprint 4 — Orchestration graph & approval gate (follow-on from Issue 1)

**Symptom:** After fixing Issue 1 (pointing `DATABASE_URL`/`REDIS_URL` at `localhost` instead of the Compose service name `postgres`), startup logged:
```
Postgres checkpointer unavailable (connection failed: connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "wpa" ...); using in-memory checkpointer (paused tasks will NOT survive a restart).
```

**Root cause:** Docker Desktop was still not running (confirmed via `docker ps` failing to reach the daemon), but something was already listening on `localhost:5432`. `Get-NetTCPConnection -LocalPort 5432` + `Get-Process` identified a **native Windows PostgreSQL 17 install** (`postgres.exe`, `C:\Program Files\PostgreSQL\17\`) already bound to port 5432 — a separate, pre-existing instance unrelated to this project's `docker-compose.yml`. It has no `wpa` role/password matching what `backend/.env`'s `DATABASE_URL` expects (that role only gets created automatically by the Postgres Docker image's first-boot init, per `docker-compose.yml`'s `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` env vars).

**Solution (user chose: use the existing local Postgres install rather than fight the port with Docker):**
1. Create the missing role/database directly in the local Postgres 17 server using its native `psql`:
   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -c "CREATE USER wpa WITH PASSWORD 'wpa';"
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE wpa OWNER wpa;"
   ```
2. Run Alembic migrations against the new database (Alembic reads `DATABASE_URL` from the same settings/`.env`, no hardcoded url in `alembic.ini`):
   ```powershell
   cd backend
   uv run alembic upgrade head
   ```
3. Restart the backend (`uv run .\main.py`).

**Caveat / follow-up:** the project's `docker-compose.yml` uses the `pgvector/pgvector:pg16` image, which ships the `vector` extension; the native Windows Postgres 17 install does not have `pgvector` installed. No migration currently uses a vector column, so this isn't blocking yet — but before any future sprint adds pgvector-backed embeddings, either install the `pgvector` extension into this native server or go back to running Postgres via Docker Compose.

**Status:** Resolved, pending the user running the two `psql` commands + `alembic upgrade head` above (not run by the agent — requires the local Postgres admin password, which was intentionally not shared in this session).

**Recurrence (same session, later restart):** Backend was restarted again and logged the *identical* `password authentication failed for user "wpa"` error. Confirmed with the user this is not a new failure mode — the `CREATE USER`/`CREATE DATABASE` commands above simply had not been run yet. No code/config change needed; this is purely a "run the setup commands, then restart" step.

**Final resolution — switched approach to Docker Compose Postgres instead of the native install:**
The user decided not to touch the native `postgresql-x64-17` Windows service (other local work may depend on it) and not to run manual `psql` role-creation against it. Instead, Postgres now runs via this project's Docker Compose, published on the host on a **non-conflicting port (5433)** so it coexists with the native install still listening on 5432:
1. `docker-compose.yml` — changed the `postgres` service's port mapping from `"5432:5432"` to `"5433:5432"` (container-internal port is still 5432; only the host-published port changed, so the in-container `DATABASE_URL` used when the backend itself runs inside Compose — `postgres:5432` — is unaffected).
2. `backend/.env` — `DATABASE_URL` updated to `postgresql+asyncpg://wpa:wpa@localhost:5433/wpa` to match the new host port.
3. Started Docker Desktop (was not running) and confirmed the daemon was reachable before proceeding.
4. `docker compose up -d postgres redis` — needed 3 retries; the image pull intermittently failed with `failed to copy: local error: tls: bad record MAC` (a transient TLS/network error during layer download, unrelated to project config — each retry resumed from cached layers and eventually completed).
5. Verified the `wpa` role/database exist automatically in the container (Compose sets `POSTGRES_USER=wpa`/`POSTGRES_PASSWORD=wpa`/`POSTGRES_DB=wpa` on first boot): `docker exec wordpress-automation-postgres-1 psql -U wpa -d wpa -c "SELECT current_user, current_database();"`.
6. Ran `uv run alembic upgrade head` against the new database — applied `0001` (create wp_sites) and `0002` (create tasks) cleanly.
7. Restarted the backend — no more "Postgres checkpointer unavailable" warning; it now uses the real Postgres-backed checkpointer.

**Status:** Resolved. Postgres and Redis run via Docker Compose on ports 5433/6379 respectively, alongside the pre-existing native Postgres install (untouched, still on 5432). If Docker Desktop is restarted, remember to run `docker compose up -d postgres redis` again before starting the backend.

---

## Issue 4 — "Create Elementor page" fails: `No WordPress site registered with slug 'sandbox'` (and a chain of issues behind it)

**Sprint:** Sprint 3 (WP REST/WP-CLI wrappers, credential storage) and Sprint 5 (Elementor JSON generation skill)

**Symptom:** Calling the "create Elementor page" tool with `site_slug: "sandbox"` failed immediately with:
```
No WordPress site registered with slug 'sandbox'.
```
raised from `get_site_credentials()` in `app/wp/credentials.py` — expected, since no site had ever been registered. Getting from that error to an actually-working end-to-end write surfaced five more issues, each blocking the next:

**1. `CREDENTIAL_ENCRYPTION_KEY` was empty.** Registering a site (`POST /api/wp/sites`) encrypts the Application Password at rest via `app/crypto.py`'s `Fernet` cipher, which raises `EncryptionKeyMissingError` if the key isn't set. Fixed by generating one (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and adding it to `backend/.env`.

**2. The local WP sandbox stack was never started.** Only `postgres`/`redis` were up (from Issue 3); `wp-db`, `wordpress`, `wp-init`, and `wpcli` (defined in `docker-compose.yml`) had never been brought up. Started with `docker compose up -d wp-db wordpress wp-init wpcli`; hit the same intermittent `tls: bad record MAC` pull errors as Issue 3 — resolved the same way, by retrying `docker pull` per-image until each succeeded, then `docker compose up -d` again (layers cache across attempts).

**3. Bug: `wp-init` service was missing `user: root`.** WordPress installed fine, but `wp plugin install elementor` failed with directory permission errors (`Unable to create directory wp-content/uploads/...`, `Could not create directory "wp-content/upgrade"`). The `wpcli` service (same image) explicitly sets `user: root` "so WP-CLI accepts `--allow-root`" per its own comment, but `wp-init` didn't — an inconsistency/bug in `docker-compose.yml`. Fixed by adding `user: root` to the `wp-init` service too. (Immediate unblock for the already-installed site: ran `wp plugin install elementor --activate` directly via the already-root `wpcli` container instead of re-running `wp-init`.)

**4. WP REST API (`/wp-json/...`) returned raw HTML, not JSON.** A fresh WP install defaults to the "Plain" permalink structure, which doesn't enable the pretty-URL rewrite rules `/wp-json/` needs — requests fell through to the homepage. Fixed via WP-CLI: `wp rewrite structure '/%postname%/'` + `wp rewrite flush --hard`.

**5. Application Passwords were disabled for the site.** Even with a valid Application Password, every authenticated REST call returned `rest_not_logged_in` / `rest_cannot_create`. Root cause: WP core's `wp_is_application_passwords_supported()` returns `is_ssl() || 'local' === wp_get_environment_type()` — the sandbox runs over plain HTTP with no `WP_ENVIRONMENT_TYPE` set, so it evaluated to `false` and WP silently refused to authenticate the Application Password. Fixed by adding `define( 'WP_ENVIRONMENT_TYPE', 'local' );` to `wp-config.php` directly (for the already-running container) **and** adding `WORDPRESS_CONFIG_EXTRA: "define( 'WP_ENVIRONMENT_TYPE', 'local' );"` to the `wordpress` service in `docker-compose.yml` so fresh installs get it automatically (the official image writes `WORDPRESS_CONFIG_EXTRA` verbatim into `wp-config.php` on first boot).

**6. Bug: `LocalDockerExecutor.run()` crashed with an empty-message `NotImplementedError` on Windows.** Once auth worked, page creation still failed at the post-write `wp elementor flush-css` step, with `"Tool error: "` (blank detail — because `str(NotImplementedError())` with no args is `""`, which made this genuinely hard to diagnose until a temporary `traceback.print_exc()` was added). Root cause: `app/wp/wpcli.py`'s `LocalDockerExecutor.run()` used `asyncio.create_subprocess_exec()` to shell out to `docker exec`. On Windows, `asyncio` subprocess support requires the `ProactorEventLoop`; uvicorn's `--reload` mode spawns each worker via `multiprocessing`'s `"spawn"` context as a genuinely fresh process, which starts on a `SelectorEventLoop` that doesn't support subprocesses at all — raising `NotImplementedError` the instant a subprocess is created. (Confirmed the sibling `SshExecutor.run()` never had this problem, because it already used `asyncio.to_thread()` with a blocking call instead of the asyncio subprocess API — an existing, working pattern in the same file.) Setting `asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())` at import time in `app/main.py` was tried first and did **not** work — by the time uvicorn's reload-spawned child process imports `app.main`, `asyncio.run()` has already created its event loop under the default policy, so the fix arrives too late. The actual fix: rewrote `LocalDockerExecutor.run()` to match `SshExecutor`'s existing pattern — a synchronous `subprocess.run()` call wrapped in `asyncio.to_thread()` — which sidesteps the Windows asyncio-subprocess/event-loop-policy issue entirely and needed no uvicorn/event-loop configuration at all.

**Solution summary:**
- `backend/.env`: added `CREDENTIAL_ENCRYPTION_KEY`.
- `docker-compose.yml`: added `user: root` to `wp-init`; added `WORDPRESS_CONFIG_EXTRA` (sets `WP_ENVIRONMENT_TYPE=local`) to `wordpress`.
- `app/wp/wpcli.py`: `LocalDockerExecutor.run()` now uses `asyncio.to_thread(subprocess.run, ...)` instead of `asyncio.create_subprocess_exec()`.
- Registered the sandbox site: `POST /api/wp/sites` with `slug=sandbox`, `base_url=http://localhost:8080`, `wp_username=admin`, a real Application Password generated via `wp user application-password create admin agent --porcelain`, `wpcli_transport=local_docker`.
- Ran `wp rewrite structure` + `wp rewrite flush --hard` against the sandbox for pretty permalinks.

**Verified:** `POST /api/wp/execute` with `wp_create_elementor_page` against `site_slug: "sandbox"` now returns `{"status": "applied", "page": {...}, "sections": [...], "css_flushed": true}` end-to-end through the real API (no direct script bypass).

**Status:** Resolved. Note for anyone spinning up the sandbox fresh: an Application Password still must be generated and registered manually per site (Sprint 3's known caveat) — this isn't automated by `wp-init`.

---

## Issue 5 — Dashboard chat shows "I couldn't plan that: fetch failed"

**Sprint:** Sprint 2/4 — Dashboard chat UI + orchestration graph (the Next.js ↔ FastAPI bridge)

**Symptom:** Submitting a request in the dashboard's chat panel returned the assistant message `I couldn't plan that: fetch failed` instead of a plan.

**Root cause:** `"fetch failed"` is literally `err.message` from the `catch` block in `frontend/src/app/api/chat/route.ts:76-77` — it's what Node's `fetch()` throws when the underlying TCP connection can't be established at all (as opposed to a normal non-2xx HTTP response, which is handled separately and would have shown the backend's actual error detail instead). That message only ever appears when `fetch(\`${BACKEND_URL}/api/tasks\`)` couldn't reach *anything* listening on `http://localhost:8000`.

Confirmed the underlying cause was environmental, not a code bug: **Docker Desktop was not running** (again — same recurring issue as Issues 1/3/4, most likely after a machine restart, since Docker Desktop doesn't auto-start previously-running containers). With the daemon down, `postgres`, `redis`, `wp-db`, `wordpress`, and `wpcli` were all stopped. At the moment the user hit "send," nothing was listening on port 8000 at all (the backend dev process itself was either not running yet or had gone down), producing the connection-refused-style `fetch failed`. By the time this was investigated, a backend process happened to be listening again (`/health` returned 200), but `/api/wp/sites` still 500'd with a bare "Internal Server Error" because Postgres was unreachable — confirming the containers, not the backend process, were the actual gap.

**Solution:**
1. Started Docker Desktop again and waited for its daemon to become reachable.
2. `docker compose up -d postgres redis wp-db wordpress wpcli` (all services needed for the sandbox end-to-end flow; `wp-init` intentionally excluded since WordPress/Elementor were already installed in Issue 4 — re-running it is a documented no-op anyway).
3. Verified the previously-registered `sandbox` site and the WP sandbox's permalink/`WP_ENVIRONMENT_TYPE` fixes both survived, since they live in Docker volumes (`postgres_data`, `wp_data`) that persist across container stop/start — no re-registration or re-fixing needed.
4. Verified the actual dashboard code path end-to-end (not a bypass): `POST http://localhost:3000/api/chat` with a real chat message now streams back `"I've planned 1 step(s)..."` plus the real `data-plan` payload from the live backend/graph — no "fetch failed."

**Follow-up worth considering (not implemented):** this is the fourth issue in this log caused by Docker Desktop/containers not running after a restart. If this keeps recurring, consider either (a) configuring Docker Desktop's "Start containers on boot" restart policy for this project's compose stack, or (b) having the frontend's `/api/chat` route catch a connection-refused specifically and surface a clearer message than the generic "fetch failed" (e.g. "Backend unreachable — is the FastAPI server and Docker stack running?").

**Status:** Resolved for this session (Docker Desktop + full container stack back up, verified through the real dashboard proxy). The underlying "containers don't survive a machine/Docker restart" pattern is environmental and will recur — see follow-up above.

---

## Issue 6 — Switch the dev site from the Docker sandbox to a real local WordPress install (`digi.local`, via Local by WP Engine)

**Sprint:** Sprint 3 — WP REST/WP-CLI wrappers (extends the WP-CLI transport abstraction with a third transport)

**Context:** The user has a separate, non-Docker WordPress install managed by "Local by WP Engine" — site `digi` at `http://digi.local`, PHP 8.2.29, MySQL 8.4.0 via nginx — and asked to make it the primary dev site instead of the Docker `sandbox` site from Issue 4.

**Problem found before registering:** the only two `WpCliTransport` options were `ssh` (real remote hosts via Fabric/Paramiko) and `local_docker` (`docker exec` into *this project's own* `wpcli` sandbox container). Neither fits `digi.local` — it's not reachable over SSH, and registering it with `local_docker` would have silently pointed every WP-CLI action (plugin installs, and critically the mandatory `elementor flush-css` after every Elementor write) at the **wrong WordPress install** — our Docker sandbox's database, not digi's. Caught this before it caused a wrong-site write and flagged it to the user rather than registering it misconfigured.

**Solution — added a third WP-CLI transport, `local_process`:**
1. `app/db/models.py` — added `local_process` to the `WpCliTransport` enum; added two new `WpSite` columns: `cli_cwd` (the site's working directory to run WP-CLI from) and `cli_env` (JSON-encoded extra environment variables it needs — e.g. a bundled PHP's `PHPRC`, a `PATH` prefix for its binaries). Not treated as secret (paths/config, no credentials), so stored as plain `Text`, unlike the encrypted SSH fields.
2. `alembic/versions/0003_add_local_process_transport.py` (new file; `project-structure.md` updated in the same change per AGENTS.md rule) — `ALTER TYPE wpcli_transport ADD VALUE 'local_process'` + the two new columns.
3. `app/wp/schemas.py` (`SiteCredentials`), `app/wp/credentials.py` (`_to_credentials`/`upsert_site`, JSON encode/decode for `cli_env`), and `app/api/wp_routes.py` (`SiteIn`) — threaded the two new fields through.
4. `app/wp/wpcli.py` — added `LocalProcessExecutor`: runs WP-CLI as a plain `subprocess.run()` (via `asyncio.to_thread`, matching the existing `SshExecutor`/`LocalDockerExecutor` pattern from Issue 4) in `cli_cwd`, with `cli_env` merged into the inherited environment (`PATH` is prefixed, not replaced, so the rest of the system `PATH` still resolves). Updated `build_executor()` to dispatch on the new transport.

**Setting up `digi.local` itself:**
- Found its WP-CLI binaries/env by reading Local's auto-generated `app/.envrc` (`~/Local Sites/digi/app/.envrc`): bundled PHP at `AppData/Roaming/Local/lightning-services/php-8.2.29+0/...`, WP-CLI at `Program Files (x86)/Local/resources/extraResources/bin/wp-cli/win32/wp.bat`, plus `PHPRC`/`MYSQL_HOME`/`WP_CLI_CONFIG_PATH`.
- Confirmed `digi.local`'s `wp-config.php` already defines `WP_ENVIRONMENT_TYPE = 'local'` (Local sets this itself), so — unlike Issue 4's Docker sandbox — Application Passwords and pretty permalinks already worked out of the box; no fixes needed there.
- Generated an Application Password via WP-CLI (`wp user application-password create digi agent --porcelain`) rather than the WP Admin UI, and registered `digi` with `wpcli_transport=local_process`, `wp_cli_path` set to the full `wp.bat` path, `cli_cwd` set to the site's `app/public` dir, and `cli_env` carrying `PHPRC`/`MYSQL_HOME`/`WP_CLI_CONFIG_PATH`/`PATH`.
- `frontend/.env.local` — `NEXT_PUBLIC_DEFAULT_SITE` changed from `sandbox` to `digi` (requires a frontend dev-server restart to take effect, since Next.js reads it at build/import time).

**Verified:** `POST /api/wp/execute` with `wp_create_elementor_page` against `site_slug: "digi"` returned `{"status": "applied", "page": {...}, "css_flushed": true}` — confirming both the REST write and the new `local_process` WP-CLI flush-css step work end-to-end against the real local WordPress install.

**Status:** Resolved. The Docker `sandbox` site registration was left in place (harmless, not deleted) — `digi` is now the default via the frontend env var. Note: this makes onboarding this specific machine's Local-by-WP-Engine paths brittle (`cli_cwd`/`cli_env` are absolute paths tied to this user's install) — if this site is used from another machine or Local reinstalls to a different path, `cli_env`/`wp_cli_path`/`cli_cwd` will need updating via a re-`POST /api/wp/sites` call.

---

## Issue 7 — PHP warnings on generated pages: `Undefined array key "mountain-sun"` in Elementor's `font-awesome.php`

**Sprint:** Post-Sprint-8 fix pass (Elementor richness work — the `features` section's new `icon-box` widget)

**Symptom:** User-reported, seen on a real generated page on `digi.local`:
```
Warning: Undefined array key "mountain-sun" in .../elementor/core/page-assets/data-managers/font-icon-svg/font-awesome.php on line 45
Warning: Trying to access array offset on value of type null in .../font-awesome.php on line 48
Warning: Trying to access array offset on value of type null in .../font-awesome.php on line 49
Warning: Trying to access array offset on value of type null in .../font-awesome.php on line 50
```

**Root cause:** Read `digi.local`'s actual installed `font-awesome.php` directly (`C:\Users\Web Dept\Local Sites\digi\app\public\wp-content\plugins\elementor\...`) rather than guessing. Elementor's SVG icon renderer doesn't use whatever Font Awesome version is documented publicly — it looks icons up by name in a *bundled* dataset, `elementor/assets/lib/font-awesome/json/solid.json`, pinned to **Font Awesome 5.15.3** (`Font_Awesome::LIBRARY_CURRENT_VERSION`), confirmed by reading that file too. `"mountain-sun"` is a real Font Awesome icon — but it was added in FA **6.2**, so it doesn't exist in the bundled 5.15.3 dataset `$file_data['icons']['mountain-sun']` looks up, producing `null`, hence the warnings. The generator's system prompt (added in the same richness pass that introduced icon slots) told the model to "pick a Font Awesome 6 free solid class" without any awareness that Elementor's actual icon renderer is stuck on FA5.

**Solution:**
1. Extracted the real, complete list of valid icon keys from `digi.local`'s own `solid.json` (1002 icons) and cross-checked a curated 175-icon candidate list against it — every entry confirmed present. New file: `backend/app/agent/skills/elementor/icons.py` (`ALLOWED_ICONS`, `DEFAULT_ICON = "star"`, `safe_icon()`).
2. `safe_icon()` is called defensively in `skill.py`'s `build_and_validate()` — the single choke point every `PageSpec` passes through — so **any** icon value that isn't in the verified-safe list is swapped for the default, regardless of what the model actually returned. This is a hard guarantee, not a prompt-compliance hope.
3. `generator.py`'s system prompt now lists the exact 175 allowed icon names instead of vaguely saying "Font Awesome 6."
4. **Found and fixed a second bug while verifying the first fix live:** the first version of `safe_icon()` stripped the `"fas fa-"` prefix and returned a bare name (e.g. `"camera"`). That produced a *different* PHP warning (`Undefined array key 0` at `font-awesome.php` line 19) because Elementor's own parser (`Font_Awesome::get_config()`) regex-extracts the icon name from the value via `preg_match('/fa(.*) fa-/', ...)` — it requires the full `"fas fa-camera"` form to match at all. Fixed by having `safe_icon()` always return the fully-prefixed form.
5. Added regression tests (`tests/test_elementor_skill.py`) and a scored eval check (`app/evals/scenarios/elementor.py`'s `icons_are_safe`, plus a scenario that deliberately feeds `"fas fa-mountain-sun"` as input to prove the sanitization holds).

**Verified live (twice — the fix needed a second pass):** wrote a real page with the exact offending icon (`fas fa-mountain-sun`) via the real REST pipeline against the Docker sandbox, confirmed via `docker logs` that no PHP warnings appeared, and screenshotted the result — the "Portraits" feature now shows a star icon (the safe fallback) instead of a broken one, with zero warnings.

**Status:** Resolved. `backend/tests` full suite: 114 passed, 4 skipped (one pre-existing, unrelated Docker-environment failure). Not yet re-verified against `digi.local` itself (no credentials available in this session — see the request for a page link/screenshot in the same turn this was fixed).

---

## Issue 8 — Generated pages feel "not production-level": button-color clash + theme skill has zero effect on Astra

**Sprint:** Post-Sprint-8 fix pass (same session as Issue 7 — user published 3 real pages on `digi.local` and asked for a direct design review)

**Symptom:** User reported generated pages don't look production-level. The complaint was vague, so rather than guess, published pages (ids 33/34/35 on `digi.local`) were fetched and screenshotted directly via Playwright against the live site, and the rendered HTML/CSS was inspected. Structurally the pages were actually solid (5–6 sections each: hero, features, stats, testimonials, cta_banner, footer, real copy, working icons) — the user confirmed the gap was visual/design polish, not missing content.

**Root cause (two separate things, both confirmed by inspecting the real rendered page, not assumption):**
1. **Button color clash.** Elementor's button widget has no explicit `background_color` in any of our templates, so it falls back to Elementor's own hardcoded default (a green, `#61ce70`-ish) — visually clashing with whatever accent color the rest of the page uses.
2. **The Sprint 6 theme skill has zero visible effect when the active theme is Astra.** Confirmed by grepping the live page's rendered CSS: `font-family:-apple-system,BlinkMacSystemFont,...` (Astra's own default system-font stack, not any custom font) and `--ast-global-color-0:#046bd2` (Astra's own global-color CSS custom properties). Our `applier.py` writes generic `wpa_color_*`/`wpa_font_*` `theme_mod` keys — Astra doesn't read those at all; it stores its palette/typography in its own `astra-settings` option array and a set of `--ast-global-color-N` CSS variables. This had been a *documented caveat* since Sprint 6 ("theme mods assume generic Customizer keys — theme-specific keys vary") but was never empirically confirmed against a real theme until this review. Attempting to verify this further via WP-CLI against `digi.local` hit its own snag: the bundled PHP (`Local by WP Engine`'s `php-8.2.29`) needs `PHPRC`/`MYSQL_HOME` env vars correctly set for `mysqli` to load, which wasn't fully reconstructed in this session — confirmed via rendered CSS instead, which is arguably the more direct signal anyway.

**Solution (button-color clash — fixed and live-verified):**
1. Added a `button_color` scalar slot to `hero.json` and `cta_banner.json`, wired to the button widget's `background_color` setting.
2. `generator.py`'s system prompt now tells the model: if it sets `background_color`, also pick one bold accent hex and **reuse the same `button_color` value across every button on the page** — no more per-section-random accents.
3. Added `app/evals/scenarios/elementor.py`'s `button_colors_applied` check (fails if a section set `button_color` but the built button widget doesn't carry it).
4. **Verified live:** built a page with `button_color: "#c9a15a"`, wrote it via the real REST pipeline to the Docker sandbox, screenshotted it — the button is now gold/brand-colored instead of the generic clashing green.

**Not fixed in this pass (documented, scoped follow-up):** properly wiring the theme skill to Astra (or any specific theme) needs its own research pass — Astra stores its settings as a single serialized option (`astra-settings`), which (per the lesson from Issue 6/`progress-tracker.md`'s "companion plugin" fix) likely needs the same `--format=json` treatment WP-CLI needed for Elementor's kit meta, plus reverse-engineering Astra's actual option key names before writing to it blindly. Given the fragility already found twice in this session from guessing at a third-party plugin's internal data format, this deserves a dedicated, live-verified pass rather than a quick patch.

**Status:** Button-color fix resolved and live-verified. Astra theme-integration gap documented as a follow-up, not yet scheduled. `backend/tests`: 114 passed, 4 skipped (same pre-existing unrelated failure).

---

## Issue 9 — Generated pages still look unprofessional vs. a real production site (style-only design-system upgrade)

**Sprint:** Post-Sprint-8 fix pass (direct follow-up to Issue 8 — user provided a screenshot of a real, professionally-designed notary-services site as the concrete bar to hit)

**Symptom:** User reported the generated pages were still "so un-professional" compared to a real production site, with a screenshot showing: a top-bar/badge row, icon-circle service cards with shadows, a bio/about block, a dark testimonials band with quote styling, and a multi-column footer — none of which our 9-section template library could produce, even after Issue 8's button-color fix.

**Scope decision (via `/architect`, confirmed with the user before building):** style-only upgrade — no new image-sourcing capability, so photo-based elements (hero background photo, headshot, testimonial avatars, map) stayed explicitly out of scope. Everything achievable with existing Elementor widgets (color, shadow, border-radius, icon-circle badges) was in scope.

**What shipped:**
1. **`builder.py`:** grid/stack sections now wrap their repeated items one level deeper (`section -> column -> [heading widgets..., inner section]`) so a heading/eyebrow/subheading can sit above a grid of cards — previously structurally impossible, since an Elementor section's columns lay out side by side. Reuses the fact that `validator.py` already allows a section as a column's child.
2. **Unified `accent_color`** (renamed from Issue 8's `button_color`): now drives button backgrounds *and* icon-box `primary_color` (the icon-circle background), enforced by two new eval checks (`accent_color_applied`, `accent_color_consistent`) instead of being a prompt-only convention.
3. **Card styling** (`border_radius`/`box_shadow`/`padding`) added to `features`/`testimonials`/`pricing`/`about`/`contact`; icon-circle badges (`icon-box` widget's `view: stacked`/`shape: circle`) added to `features`/`badges`.
4. **Two new section types:** `about` (bio block, no photo) and `badges` (trust-badge row); `footer` converted from plain centered text to a heading + link-column grid.
5. `generator.py`'s system prompt updated: fill headings on grid/stack sections, alternate `background_color` for visual rhythm, reuse one `accent_color` everywhere.

**Two real bugs found only by live verification (built a real page through the actual REST/WP-CLI pipeline against the Docker sandbox, not just offline validation):**
1. **`builder.py` token-fill bug:** the per-item token-fill pass (`_fill_tokens` for grid/stack items) replaced *any* unmatched `{{token}}` with `""`, including section-level scalar tokens like `{{accent_color}}` that happen to sit inside an item's cloned prototype (e.g. `icon-box`'s `primary_color`). This silently blanked `accent_color` before the later section-content fill pass ever ran, so icon-circle backgrounds rendered as Elementor's plain black/white default instead of the page's accent color — confirmed by inspecting the real stored `_elementor_data` (`"primary_color": ""`) after a live build, then visually confirmed via a Playwright screenshot of the actual rendered page. Fixed by adding a `blank_unmatched` flag: the item-level pass now leaves unmatched tokens untouched (`blank_unmatched=False`), only the final section-content pass blanks genuinely-omitted optional slots.
2. **Testimonial dark-background contrast bug:** with a dark `background_color` + light `heading_color` (a pairing the generator is instructed to use for visual rhythm), the testimonial widget's own text (quote/name/role) still rendered in Elementor's default dark gray — because `heading_color` was only ever wired to the section's own `heading`/`subheading` widgets, not to the `testimonial` widget's own color controls. Read the real widget source (`elementor/includes/widgets/testimonial.php`) to find the actual control names (`content_content_color`, `name_text_color`, `job_text_color`) and wired all three to `heading_color` in `testimonials.json`.
3. Also cross-checked the Icon Box widget's actual source (`elementor/includes/widgets/icon-box.php`) for `view`/`shape`/`primary_color`/`secondary_color` — those control names were correct as written; the failure above was in `builder.py`'s token-filling, not a wrong Elementor control name.

**Verified live:** built the exact notary-services brief (mirroring the user's screenshot) through the real `wp_create_elementor_page` tool against the Docker sandbox three times (iterating on the two bugs above), confirmed `_elementor_data` persisted correctly each time, checked `docker logs` for PHP warnings (none beyond the known unrelated `WP_ENVIRONMENT_TYPE` redefinition warning), and screenshotted the final rendered page with Playwright — hero/about/features/badges/testimonials/footer all render with consistent accent-colored icon circles, readable testimonial text on the dark band, card shadows, and section headings above every grid. Test pages and the throwaway sandbox Application Password were cleaned up afterward (the app password itself was left in place since the `sandbox` site registration now depends on it, same situation as Issue 4).

**Status:** Resolved and live-verified. `backend/tests`: 118 passed, 4 skipped (same one pre-existing, unrelated `test_local_docker_executor_command` Docker-environment failure that reproduces on `main`). Photo-based sections (real hero/about photography, testimonial avatars, map embed) remain a documented, scoped follow-up pending an image-sourcing capability.

---

## Issue 10 — Dashboard chat shows `Planning failed: 1 validation error for wp_create_elementor_page — brief Field required, input_value={'site_slug': 'digi'}`

**Sprint:** Sprint 4/7 — Orchestration graph (planner) + the thin Sprint 3 NL agent path

**Symptom:** Submitting a request in the dashboard chat (site `digi`) returned `I couldn't plan that: Planning failed: 1 validation error for wp_create_elementor_page brief Field required [type=missing, input_value={'site_slug': 'digi'}, ...]` instead of a plan.

**Root cause:** The orchestrator model (Claude, via `bind_tools`) chose `wp_create_elementor_page` but emitted a tool call whose `args` contained only `site_slug` — no `brief` key at all. Anthropic tool-use doesn't hard-guarantee every required parameter is populated the way a strict function-call validator would; when the model treats the user's whole instruction as self-evidently "the brief" it can skip re-stating it as an explicit argument. `planner.py`'s `_to_step()` passed the model's raw args straight into `TOOLS_BY_NAME[name].ainvoke(args)` (to build the write-tool preview) with no gap-filling, so the tool's own pydantic schema (`brief: str`, no default, in `app/agent/tools/wp_tools.py`) rejected the call. That `ValidationError` propagated up through `TaskManager.start()` into `app/api/task_routes.py`'s generic `except Exception as exc: raise HTTPException(400, f"Planning failed: {exc}")`, which dumps the raw pydantic error text — the same generic-exception-handler pattern already flagged as a follow-up in Issue 1. The sibling Sprint-3 path (`app/agent/wp_agent.py`'s `WpAgent.propose()`, used by `POST /api/wp/plan`) had the identical unguarded `ainvoke(args)` call and was vulnerable to the same failure.

**Solution:**
1. `backend/app/agent/orchestrator/planner.py` (`_to_step`) — now takes the original `instruction` string and, if the model's tool call is missing `brief` while the target tool's schema declares `brief` as a field (`wp_create_elementor_page`, `wp_publish_post`, `wp_apply_theme`), fills `args["brief"]` from the raw instruction before validating/previewing. The user's instruction *is* a valid plain-language brief, so this is a correct fallback, not a guess.
2. `backend/app/agent/wp_agent.py` (`WpAgent.propose`) — same fallback applied for the `/api/wp/plan` path, for consistency (both paths share `TOOLS_BY_NAME`/`WRITE_TOOL_NAMES` from `wp_agent.py`).
3. Added regression tests: `backend/tests/test_planner.py::test_plan_fills_missing_brief_from_instruction` and `backend/tests/test_wp_agent.py::test_propose_fills_missing_brief_from_instruction`, both driving a `FakeLLM` that returns `{"name": "wp_create_elementor_page", "args": {}}` (no `brief`) and asserting the step/proposal ends up with `brief` set to the instruction and a valid `needs_approval` preview instead of raising.

**Not fixed in this pass (documented, scoped follow-up):** the underlying `except Exception` → generic `400 "Planning failed: ..."` pattern in both `task_routes.py` and `wp_routes.py` still surfaces raw exception text (including any *other* missing required argument, on any other tool) verbatim to the end user. This fix specifically closes the `brief` gap since that's the field every brief-taking write tool shares and the instruction is always a valid substitute; a broader error-classification pass (distinguishing "model produced an invalid tool call" from real infra errors, per Issue 1's same follow-up) is still open.

**Verified:** `backend/tests`: 122 passed, 4 skipped (targeted `test_planner.py`/`test_wp_agent.py` run first — 11 passed — then full suite; same one pre-existing, unrelated `test_local_docker_executor_command` Docker-environment failure noted in Issues 4/7/9 reproduces on `main`, unaffected by this change).

**Status:** Resolved.
