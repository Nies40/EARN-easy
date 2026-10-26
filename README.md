# Easyearn

The Nies Technologies user platform, built with **FastAPI, PostgreSQL, and a plain HTML/CSS/JavaScript frontend**. This is the project foundation, not a production-ready or complete V1 release.

The backend implements registration, login/logout, email verification, password recovery, and verified-only dashboard access. The frontend still has the signup/login and account screens; verification, recovery, and dashboard screens remain frontend work. See the [authentication API contract](docs/AUTHENTICATION.md) and [V1 roadmap](docs/ROADMAP.md).

## Prerequisites

- Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/).
- PostgreSQL, or Docker with Compose for the included local PostgreSQL 17 service.

Dependencies and supported Python versions are defined in `backend/pyproject.toml:1`; exact dependencies are recorded in `backend/uv.lock`.

## Run locally

From the repository root:

```bash
docker compose up -d db mailpit
cd backend
cp .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open **<http://localhost:8000>**. Interactive API documentation is at **<http://localhost:8000/docs>** in development.

Read development emails in **Mailpit at <http://localhost:8025>**. It captures SMTP messages locally; no domain or email-provider account is needed. Its SMTP port is `1025`, and both Mailpit ports are bound to `127.0.0.1` (`compose.yaml:18`).

If PostgreSQL is already installed, skip the Docker command, create a database and application role, and update `DATABASE_URL` in `backend/.env` before running migrations. The Compose credentials are **local-development defaults only**; the database port is bound to `127.0.0.1` (`compose.yaml:1`).

With an existing PostgreSQL installation, run `docker compose up -d mailpit` separately or configure your own local SMTP listener. Apply `uv run alembic upgrade head` to an existing project database too; migration `0002` adds account token tables without changing existing users. Existing accounts with no verification timestamp must verify their email before dashboard access.

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
│   │   └── modules/
│   │       ├── auth/            # Request schemas, routes, sessions, auth service
│   │       ├── dashboard/       # Verified-account dashboard endpoint
│   │       └── users/           # User model and database queries
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
│   └── ROADMAP.md
└── compose.yaml                # Local PostgreSQL and Mailpit
```

See [architecture](docs/ARCHITECTURE.md) for module responsibilities and extension conventions.

## Configuration

Settings load from `backend/.env`; process environment variables take precedence. Do not commit real credentials. Source: `backend/app/core/config.py:11`.

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

Account email settings are in `backend/app/core/config.py:26` and `backend/.env.example`:

- `EMAIL_VERIFICATION_TTL_SECONDS=86400`: verification links last 24 hours.
- `PASSWORD_RESET_TTL_SECONDS=1800`: reset links last 30 minutes.
- `AUTH_EMAIL_COOLDOWN_SECONDS=60`: minimum interval between emails of the same type per account.
- `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_TLS_MODE=none`: local Mailpit defaults.
- `SMTP_FROM_EMAIL=no-reply@example.com`: development sender only.
- `SMTP_TIMEOUT_SECONDS=10`: SMTP connection/command timeout.
- Optional `SMTP_USERNAME` and `SMTP_PASSWORD` must be supplied together.

Production requires `SMTP_TLS_MODE=starttls` or `ssl` and a non-placeholder sender address. Select a managed SMTP provider and verify your sending domain before enabling real outbound mail; check that the provider permits your business model.

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

## Development checks

Run inside `backend/`:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

Most tests use an isolated in-memory SQLite database and capture outgoing messages without SMTP (`backend/tests/conftest.py:25`). PostgreSQL concurrency tests skip unless `TEST_DATABASE_URL` is explicitly set. Run them against a development/test database:

```bash
TEST_DATABASE_URL=postgresql+psycopg://easyearn:easyearn_dev_password@localhost:5432/easyearn uv run pytest tests/integration -q
```

The integration fixture creates a uniquely named schema per test and drops only that schema afterward; its database role needs schema-creation permission (`backend/tests/integration/conftest.py:13`). Never use production credentials for tests. `alembic check` separately requires a running, migrated PostgreSQL database and checks for model/schema drift.

Create a migration after changing models:

```bash
uv run alembic revision --autogenerate -m "describe the change"
# Review the generated migration before applying it.
uv run alembic upgrade head
```

## Security and release status

- Passwords use bcrypt cost 12, with the 72-byte bcrypt limit validated explicitly.
- Session, verification, and password-reset tokens are stored only as SHA-256 hashes in PostgreSQL. Browser cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production; tokens are not stored in browser local storage.
- Database uniqueness constraints, bound ORM queries, request validation, host/origin checks, and frontend security headers provide the initial security baseline.
- Dashboard access requires verified email. Resetting a password revokes every session for that account and does not mark email verified or automatically sign in.
- Email requests have per-account cooldowns, but shared/IP-based login/signup/recovery throttling is still required. Expired-session/token cleanup and production deployment configuration also remain pending.
- SMTP delivery is best-effort via in-process background tasks, not a durable queue. Delivery failures are logged without message/token contents; users may request a replacement after the cooldown. Add reliable queued delivery and retry handling before public launch.
- The retained Terms and Privacy links do not have published pages yet. Publish reviewed policies before accepting real registrations.
- The previous Node/SQLite prototype has been replaced. No legacy account data is automatically migrated.

Do not deploy this foundation as a finished secure platform. Complete the [launch checklist](docs/ROADMAP.md) and validate security and performance on the actual hosting environment; no platform can guarantee “100% secure” data or instant login under all conditions.
