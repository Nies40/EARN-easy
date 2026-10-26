# Easyearn

The Nies Technologies user platform, built with **FastAPI, PostgreSQL, and a plain HTML/CSS/JavaScript frontend**. This is the project foundation, not a production-ready or complete V1 release.

Registration, email-or-username login, logout, and a basic signed-in account panel are implemented. Email verification, password recovery, and a full dashboard are still planned; see [V1 roadmap](docs/ROADMAP.md).

## Prerequisites

- Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/).
- PostgreSQL, or Docker with Compose for the included local PostgreSQL 17 service.

Dependencies and supported Python versions are defined in `backend/pyproject.toml:1`; exact dependencies are recorded in `backend/uv.lock`.

## Run locally

From the repository root:

```bash
docker compose up -d db
cd backend
cp .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open **<http://localhost:8000>**. Interactive API documentation is at **<http://localhost:8000/docs>** in development.

If PostgreSQL is already installed, skip the Docker command, create a database and application role, and update `DATABASE_URL` in `backend/.env` before running migrations. The Compose credentials are **local-development defaults only**; the database port is bound to `127.0.0.1` (`compose.yaml:1`).

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
│   │   └── modules/
│   │       ├── auth/            # Request schemas, routes, sessions, auth service
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
│   └── ROADMAP.md
└── compose.yaml                # Local PostgreSQL only
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

## API

Routes are registered in `backend/app/api/router.py:10` and `backend/app/modules/auth/router.py:32`.

| Method | Endpoint      | Purpose                                         |
| ------ | ------------- | ----------------------------------------------- |
| `POST` | `/api/signup` | Register and start a session                    |
| `POST` | `/api/login`  | Sign in with `identifier` and `password`        |
| `GET`  | `/api/me`     | Read the authenticated user                     |
| `POST` | `/api/logout` | Revoke the current session and clear its cookie |
| `GET`  | `/api/health` | Check database connectivity                     |

Signup requires `name`, `email`, and `password`. The existing username and phone fields are optional. Login's `identifier` accepts either an email or username. Request/response schemas: `backend/app/modules/auth/schemas.py:13`.

## Development checks

Run inside `backend/`:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

The tests use an isolated, in-memory SQLite database and do not connect to the configured PostgreSQL database (`backend/tests/conftest.py:24`). `alembic check` requires a running, migrated PostgreSQL database and checks for model/schema drift; it does not replace integration testing.

Create a migration after changing models:

```bash
uv run alembic revision --autogenerate -m "describe the change"
# Review the generated migration before applying it.
uv run alembic upgrade head
```

## Security and release status

- Passwords use bcrypt cost 12, with the 72-byte bcrypt limit validated explicitly.
- Random session tokens are stored only as SHA-256 hashes in PostgreSQL. Browser cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production; tokens are not stored in browser local storage.
- Database uniqueness constraints, bound ORM queries, request validation, host/origin checks, and frontend security headers provide the initial security baseline.
- Email verification is **not enforced yet**. There is no password recovery, authentication throttling, expired-session cleanup job, or production deployment configuration yet.
- The retained Terms and Privacy links do not have published pages yet. Publish reviewed policies before accepting real registrations.
- The previous Node/SQLite prototype has been replaced. No legacy account data is automatically migrated.

Do not deploy this foundation as a finished secure platform. Complete the [launch checklist](docs/ROADMAP.md) and validate security and performance on the actual hosting environment; no platform can guarantee “100% secure” data or instant login under all conditions.
