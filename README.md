# Easyearn

The Nies Technologies user platform, built with **FastAPI, PostgreSQL, and a plain HTML/CSS/JavaScript frontend**. This is the project foundation, not a production-ready or complete V1 release.

The backend implements registration, login/logout, email verification, password recovery, and verified-only dashboard access. The frontend still has the signup/login and account screens; verification, recovery, and dashboard screens remain frontend work. See the [authentication API contract](docs/AUTHENTICATION.md) and [V1 roadmap](docs/ROADMAP.md).

## Prerequisites

- Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/).
- PostgreSQL and Redis, or Docker with Compose for the included local services.

Dependencies and supported Python versions are defined in `backend/pyproject.toml:1`; exact dependencies are recorded in `backend/uv.lock`.

## Run locally

From the repository root:

```bash
docker compose up -d db mailpit redis
cd backend
cp .env.example .env
uv sync --locked
uv run python -m app.workers.email --generate-key
```

Put the printed JSON array in `EMAIL_OUTBOX_KEYS` in `backend/.env`. Keep it secret and stable across restarts; API and worker processes must share the key ring. No development fallback key is provided. Then run:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-proxy-headers
```

Open **<http://localhost:8000>**. Interactive API documentation is at **<http://localhost:8000/docs>** in development.

In a second terminal, from `backend/`, start the delivery and maintenance worker:

```bash
uv run python -m app.workers.email
```

The API queues encrypted messages; it never sends SMTP mail inside the request. Without a running worker, mail remains queued. See [email delivery and operations](docs/EMAIL_OUTBOX.md) for retries, key rotation, monitoring, cleanup, and crash behavior.

Read development emails in **Mailpit at <http://localhost:8025>**. It captures SMTP messages locally; no domain or email-provider account is needed. Its SMTP port is `1025`, and both Mailpit ports are bound to `127.0.0.1` (`compose.yaml:18`).

If PostgreSQL is already installed, skip the Docker command, create a database and application role, and update `DATABASE_URL` in `backend/.env` before running migrations. The Compose credentials are **local-development defaults only**; the database port is bound to `127.0.0.1` (`compose.yaml:1`).

With an existing PostgreSQL installation, run `docker compose up -d mailpit redis` separately or configure your own local SMTP and Redis services. Apply `uv run alembic upgrade head` to an existing project database too; migration `0003` adds the encrypted outbox. Existing accounts with no verification timestamp must verify their email before dashboard access. Never roll back the outbox migration while it holds messages you need to deliver.

Redis is required for signup, login, verification, and password recovery, including local development. Start it before testing those flows; if it is unavailable they return `503` rather than bypassing abuse protection. Logout and account reads remain available. The local Redis service binds to `127.0.0.1:6379` and stores only temporary counters (`compose.yaml:24`). See [rate limiting](docs/RATE_LIMITING.md) for defaults, proxy configuration, and failure behavior. No PostgreSQL migration is needed for rate limiting.

FastAPI serves both the frontend and API from the same origin. Do not open the HTML file directly. Node.js is no longer required.

## Project structure

```text
earn-easy/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application factory and frontend serving
│   │   ├── api/                 # Shared routing, dependencies, and HTTP errors
│   │   ├── core/                # Settings, password/token helpers, middleware
│   │   ├── db/                  # SQLAlchemy metadata and connection pooling
│   │   ├── integrations/        # Provider-independent SMTP email adapter
│   │   ├── modules/
│   │   │   ├── auth/            # Request schemas, routes, sessions, auth service
│   │   │   ├── dashboard/       # Verified-account dashboard endpoint
│   │   │   ├── outbox/          # Encrypted jobs, retries, and bounded cleanup
│   │   │   └── users/           # User model and database queries
│   │   └── workers/            # Standalone delivery/maintenance process
│   ├── migrations/             # Versioned Alembic database migrations
│   ├── tests/                  # Isolated automated tests
│   ├── .env.example
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── index.html              # Existing signup/login design
│   └── assets/
│       ├── css/
│       ├── js/
│       └── images/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AUTHENTICATION.md
│   ├── CI.md
│   ├── EMAIL_OUTBOX.md
│   ├── RATE_LIMITING.md
│   └── ROADMAP.md
└── compose.yaml                # Local PostgreSQL, Mailpit, and Redis
```

See [architecture](docs/ARCHITECTURE.md) for module responsibilities and extension conventions.

## Configuration

Settings load from `backend/.env`; process environment variables take precedence. Do not commit real credentials. Source: `backend/app/core/config.py:22`.

| Variable              | Default                      | Purpose                                                  |
| --------------------- | ---------------------------- | -------------------------------------------------------- |
| `APP_ENV`             | `development`                | `development`, `test`, or `production`                   |
| `APP_URL`             | `http://localhost:8000`      | Exact browser origin; must use HTTPS in production       |
| `DATABASE_URL`        | Local Compose connection     | SQLAlchemy URL using `postgresql+psycopg://`             |
| `ALLOWED_HOSTS`       | `["localhost", "127.0.0.1"]` | JSON list of allowed hostnames, without schemes or ports |
| `SESSION_COOKIE_NAME` | `easyearn_session`           | Authentication cookie name                               |
| `SESSION_TTL_SECONDS` | `604800`                     | Absolute session lifetime: seven days by default         |
| `DB_POOL_SIZE`        | `10`                         | Persistent database connections per application process  |
| `DB_MAX_OVERFLOW`     | `10`                         | Additional database connections per application process  |

When changing the application host or port, update `APP_URL` too. Add a new hostname to `ALLOWED_HOSTS` when needed. No cross-origin frontend is configured.

Account email settings are in `backend/app/core/config.py:40` and `backend/.env.example`:

- `EMAIL_VERIFICATION_TTL_SECONDS=86400`: verification links last 24 hours.
- `PASSWORD_RESET_TTL_SECONDS=1800`: reset links last 30 minutes.
- `AUTH_EMAIL_COOLDOWN_SECONDS=60`: minimum interval between emails of the same type per account.
- `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_TLS_MODE=none`: local Mailpit defaults.
- `SMTP_FROM_EMAIL=no-reply@example.com`: development sender only.
- `SMTP_TIMEOUT_SECONDS=10`: SMTP connection/command timeout.
- Optional `SMTP_USERNAME` and `SMTP_PASSWORD` must be supplied together.

Production requires `SMTP_TLS_MODE=starttls` or `ssl` and a non-placeholder sender address. Select a managed SMTP provider and verify your sending domain before enabling real outbound mail; check that the provider permits your business model.

Authentication limits and Redis connection settings are configurable in `backend/.env.example` and `backend/app/core/config.py:50`. Defaults are a shared 60-second window, endpoint-specific attempt limits, and `REDIS_URL=redis://localhost:6379/0`. Every API worker must use the same Redis database, key prefix, environment, and quota configuration. The app ignores raw forwarded-IP headers; keep `--no-proxy-headers` for direct/local access and configure trusted proxies explicitly for deployment.

`MAX_REQUEST_BODY_BYTES=20480` caps API bodies, including streamed requests, before JSON validation or SQL. Oversized requests receive `413`. This does not replace proxy connection, concurrency, or slow-request timeouts. `EMAIL_OUTBOX_KEYS` is required at API/delivery-worker startup; the other worker settings and defaults are documented in [email operations](docs/EMAIL_OUTBOX.md).

## API

Routes are registered in `backend/app/api/router.py:10` and `backend/app/modules/auth/router.py:47`.

| Method | Endpoint      | Purpose                                         |
| ------ | ------------- | ----------------------------------------------- |
| `POST` | `/api/signup` | Register and start a session                    |
| `POST` | `/api/login`  | Sign in with `identifier` and `password`        |
| `GET`  | `/api/me`     | Read the authenticated user                     |
| `POST` | `/api/logout` | Revoke the current session and clear its cookie |
| `GET`  | `/api/health` | Check database connectivity                     |

Signup requires `name`, `email`, and `password`. The existing username and phone fields are optional. Login's `identifier` accepts either an email or username. Request/response schemas: `backend/app/modules/auth/schemas.py:37`.

The verification, recovery, and verified-only `/api/dashboard` endpoints are documented in the [authentication API contract](docs/AUTHENTICATION.md). Unverified accounts can still sign in, read `/api/me`, request verification, and sign out.

Protected authentication POST requests may return `429` with `Retry-After`, or `503` with `Retry-After: 5` if the shared limiter is unavailable. IP-based limits apply before body validation and database access; the existing per-account email cooldowns still apply too.

## Development checks

Run inside `backend/`:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

Most tests use an isolated in-memory SQLite database, capture messages through an explicitly invoked test worker, and inject a Redis test double (`backend/tests/conftest.py:35`). Tests generate temporary encryption keys in their own process; the application has no fallback key or process-local quota fallback. PostgreSQL tests skip unless `TEST_DATABASE_URL` is explicitly set, and live Redis tests skip unless `TEST_REDIS_URL` is set. Run the integration checks against local development services:

```bash
TEST_DATABASE_URL=postgresql+psycopg://easyearn:easyearn_dev_password@localhost:5432/easyearn \
TEST_REDIS_URL=redis://localhost:6379/0 \
uv run pytest tests/integration -q
```

The PostgreSQL fixture creates a uniquely named schema per test and drops only that schema afterward; its database role needs schema-creation permission (`backend/tests/integration/conftest.py:14`). Redis tests use uniquely prefixed, short-lived keys and never flush a database. Never use production credentials for tests. `alembic check` separately requires a running, migrated PostgreSQL database and checks for model/schema drift.

GitHub Actions is configured to run the backend checks on Python 3.12–3.14 with disposable PostgreSQL/Redis services, migration round trips, and a strict runtime-dependency advisory audit. Actions are commit-pinned and use no production secrets. See [CI and dependency security](docs/CI.md) for local audit commands and the branch-protection setup still needed after the first hosted run.

Create a migration after changing models:

```bash
uv run alembic revision --autogenerate -m "describe the change"
# Review the generated migration before applying it.
uv run alembic upgrade head
```

## Security and release status

- Passwords use bcrypt cost 12, with the 72-byte bcrypt limit validated explicitly.
- Authentication tables store only SHA-256 token hashes. Delivery jobs hold token links only inside authenticated encryption, with encryption keys kept outside PostgreSQL. Browser cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production; tokens are not stored in browser local storage.
- Database uniqueness constraints, bound ORM queries, request validation, host/origin checks, and frontend security headers provide the initial security baseline.
- Dashboard access requires verified email. Resetting a password revokes every session for that account and does not mark email verified or automatically sign in.
- Authentication mutations have Redis-backed per-network quotas, body-size limits, and per-account email cooldowns. Tune quotas and add perimeter protection; these are not complete DDoS protection.
- SMTP uses a transactional encrypted outbox with bounded retries and crash recovery. Delivery is at-least-once, not exactly-once; duplicate messages are possible after an ambiguous SMTP outcome. Sensitive payloads are erased on terminal states. A supervised worker is required for delivery and periodic cleanup.
- Production deployment, backup/restore testing, required hosted CI checks, key management, monitoring, and a deployment-specific security review remain launch requirements.
- The retained Terms and Privacy links do not have published pages yet. Publish reviewed policies before accepting real registrations.
- The previous Node/SQLite prototype has been replaced. No legacy account data is automatically migrated.

Do not deploy this foundation as a finished secure platform. Complete the [launch checklist](docs/ROADMAP.md) and validate security and performance on the actual hosting environment; no platform can guarantee “100% secure” data or instant login under all conditions.
