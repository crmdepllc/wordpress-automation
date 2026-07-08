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
