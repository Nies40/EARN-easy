# Architecture

## Decisions

- **Modular monolith:** one FastAPI application, one PostgreSQL database, and one same-origin frontend. Separate services and a JavaScript framework are not needed for the current scope.
- **Python backend:** FastAPI replaces the original Express prototype, as requested.
- **PostgreSQL:** replaces the original document's MySQL choice, as selected during setup.
- **Revocable cookie sessions:** server-side sessions suit the browser app without introducing JWT storage or refresh-token infrastructure.

## Component map

| Component        | Responsibility                                                                 | Source                                                                                |
| ---------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| App factory      | Wire routes, middleware, database sessions, lifecycle, and public files        | `backend/app/main.py:18`                                                              |
| API dependencies | Supply request-scoped database sessions and authenticated users                | `backend/app/api/dependencies.py:15`                                                  |
| Settings         | Read environment configuration and validate deployment settings                | `backend/app/core/config.py:11`                                                       |
| Security helpers | Hash passwords and generate/hash random session tokens                         | `backend/app/core/security.py:7`                                                      |
| Middleware       | Reject unexpected browser origins; set security and cache headers              | `backend/app/core/middleware.py:8`                                                    |
| Auth routes      | Translate HTTP requests/responses and set or clear cookies                     | `backend/app/modules/auth/router.py:17`                                               |
| Auth service     | Register, authenticate, rotate, expire, and revoke sessions                    | `backend/app/modules/auth/service.py:23`                                              |
| Users            | Define user persistence and identifier queries                                 | `backend/app/modules/users/models.py:10`, `backend/app/modules/users/repository.py:7` |
| Migrations       | Apply reviewed, versioned schema changes                                       | `backend/migrations/env.py:31`                                                        |
| Frontend         | Render forms, call the API, and update account state safely with `textContent` | `frontend/index.html`, `frontend/assets/js/auth.js`                                   |

## Request and data flow

```text
Browser → security/host middleware → API route → auth service → user queries / SQLAlchemy
                                                                     ↓
                                                                 PostgreSQL
```

Routes handle HTTP concerns; services handle authentication decisions and transaction boundaries. ORM queries use bound values rather than interpolated SQL. Synchronous endpoints run database and bcrypt work in FastAPI's thread pool rather than blocking async handlers.

Registration validates and normalizes the submitted identifiers, hashes the password, and commits the user and session together. Lowercase checks and unique database constraints protect normalized email/username identifiers, including concurrent duplicate registrations.

Successful signup or login places an opaque token in an `HttpOnly` cookie. Only its hash is persisted. `/api/me` joins an unexpired session to its user; login rotates the caller's previous session and logout deletes it. Sessions have absolute expiry, not sliding expiry. Expired records are ignored but still need scheduled cleanup.

## Database boundaries

- `users`: UUID identifier, name, normalized unique email, optional normalized unique username, optional phone, password hash, verification timestamp, and creation timestamp.
- `user_sessions`: hashed token, user foreign key, expiry, and creation timestamp. Expiry and user ID are indexed; deleting a user cascades to their sessions.
- Tables are created by Alembic migrations, **not** by application startup.
- Connection pools belong to each application process. Account for the sum of all workers' pool sizes when configuring PostgreSQL connection limits.

## Extension conventions

Add feature code under `backend/app/modules/<feature>/`. Keep request schemas, HTTP routes, service logic, and persistence separate where each is needed; do not create empty layers in advance. Include new routers in `backend/app/api/router.py` and import new models in `backend/migrations/env.py` so Alembic sees them.

Future email verification and password reset should use expiring, single-use tokens stored as hashes. Email delivery should have its own adapter boundary; it must not be simulated as successful delivery. These capabilities are **not implemented** in the current foundation.

Only the HTML entry point and `frontend/assets/` are served publicly. Backend code, credentials, and migrations remain outside the static file mount. Interactive API documentation is disabled in production.
