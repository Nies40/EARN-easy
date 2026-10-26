# Architecture

## Decisions

- **Modular monolith:** one FastAPI application, one PostgreSQL database, and one same-origin frontend. Separate services and a JavaScript framework are not needed for the current scope.
- **Python backend:** FastAPI replaces the original Express prototype, as requested.
- **PostgreSQL:** replaces the original document's MySQL choice, as selected during setup.
- **Revocable cookie sessions:** server-side sessions suit the browser app without introducing JWT storage or refresh-token infrastructure.

## Component map

| Component        | Responsibility                                                                 | Source                                                                                |
| ---------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| App factory      | Wire routes, middleware, database sessions, lifecycle, and public files        | `backend/app/main.py:21`                                                              |
| API dependencies | Supply request-scoped database sessions and authenticated users                | `backend/app/api/dependencies.py:20`                                                  |
| Settings         | Read environment configuration and validate deployment settings                | `backend/app/core/config.py:21`                                                       |
| Security helpers | Hash passwords and generate/hash random session tokens                         | `backend/app/core/security.py:7`                                                      |
| Middleware       | Reject unexpected browser origins; set security and cache headers              | `backend/app/core/middleware.py:8`                                                    |
| Auth routes      | Translate HTTP requests/responses and set or clear cookies                     | `backend/app/modules/auth/router.py:48`                                               |
| Auth service     | Register, authenticate, rotate, expire, and revoke sessions                    | `backend/app/modules/auth/service.py:48`                                              |
| Users            | Define user persistence and identifier queries                                 | `backend/app/modules/users/models.py:10`, `backend/app/modules/users/repository.py:9` |
| Migrations       | Apply reviewed, versioned schema changes                                       | `backend/migrations/env.py:35`                                                        |
| Frontend         | Render forms, call the API, and update account state safely with `textContent` | `frontend/index.html`, `frontend/assets/js/auth.js`                                   |

## Request and data flow

```text
Browser → security/host checks → auth rate limiter → API route → auth service → PostgreSQL
                                      ↓
                                    Redis
```

Routes handle HTTP concerns; services handle authentication decisions and transaction boundaries. ORM queries use bound values rather than interpolated SQL. Synchronous endpoints run database and bcrypt work in FastAPI's thread pool rather than blocking async handlers.

Authentication writes first pass through `AuthRateLimitMiddleware` (`backend/app/api/rate_limit.py:50`). It uses an asynchronous Redis client and an atomic Lua counter/expiry operation shared by workers (`backend/app/core/rate_limit.py:63`). Host/origin rejection runs before the limiter. Policies are per endpoint and source network; raw forwarded-IP headers are ignored by the app. Rejected requests do not reach validation, bcrypt, or SQL queries. Missing client addresses and Redis errors fail closed with `503`; logout and reads remain independent of Redis.

Redis stores expiring quota counters only, not user accounts or session/token data. Each app owns a bounded Redis connection pool and closes it during shutdown. The [rate-limiting guide](RATE_LIMITING.md) covers proxy trust, timeouts, restart behavior, and integration testing.

Registration validates and normalizes the submitted identifiers, hashes the password, and commits the user and session together. Lowercase checks and unique database constraints protect normalized email/username identifiers, including concurrent duplicate registrations.

Signup also creates a verification-token hash in the same transaction. Raw account tokens exist only in memory and outbound emails. Account email messages are built before commit, then handed to an SMTP adapter in a background task after the response. A failed SMTP send does not roll back a successfully registered account.

Successful signup or login places an opaque token in an `HttpOnly` cookie. Only its hash is persisted. `/api/me` joins an unexpired session to its user; login rotates the caller's previous session and logout deletes it. Sessions have absolute expiry, not sliding expiry. Expired records are ignored but still need scheduled cleanup.

`get_verified_user` protects dashboard routes while `get_current_user` permits limited account access (`backend/app/api/dependencies.py:36`). Verification does not create a new session. Password reset changes the hash, consumes the reset token, and revokes all account sessions in one transaction.

Token operations and login take the user-row lock before mutating tokens or sessions. Token consumption also uses a conditional update with `RETURNING`, checking both expiry and unused status. This prevents concurrent double use, serializes resend cooldowns, and ensures an old-password login cannot leave a session surviving a simultaneous reset (`backend/app/modules/auth/tokens.py:49`).

## Database boundaries

- `users`: UUID identifier, name, normalized unique email, optional normalized unique username, optional phone, password hash, verification timestamp, and creation timestamp.
- `user_sessions`: hashed token, user foreign key, expiry, and creation timestamp. Expiry and user ID are indexed; deleting a user cascades to their sessions.
- `email_verification_tokens` and `password_reset_tokens`: hashed token primary key, user foreign key, expiry, usage timestamp, and creation timestamp. Issuing a replacement deletes older tokens of the same purpose. Deleting a user cascades to both token tables.
- Tables are created by Alembic migrations, **not** by application startup.
- Connection pools belong to each application process. Account for the sum of all workers' pool sizes when configuring PostgreSQL connection limits.

## Extension conventions

Add feature code under `backend/app/modules/<feature>/`. Keep request schemas, HTTP routes, service logic, and persistence separate where each is needed; do not create empty layers in advance. Include new routers in `backend/app/api/router.py` and import new models in `backend/migrations/env.py` so Alembic sees them.

Email delivery is isolated behind the `EmailSender` protocol and `SMTPEmailSender` adapter (`backend/app/integrations/email.py:24`). Local Mailpit captures real SMTP traffic; tests substitute a capturing sender. The current background task is best-effort and has no persistent queue or automatic retry. Add durable delivery before public launch, without putting raw token bodies in plaintext application database rows or logs.

The [authentication contract](AUTHENTICATION.md) defines email links and the frontend screens still needed. Neither a domain nor an external email provider is required for local development.

Only the HTML entry point and `frontend/assets/` are served publicly. Backend code, credentials, and migrations remain outside the static file mount. Interactive API documentation is disabled in production.
