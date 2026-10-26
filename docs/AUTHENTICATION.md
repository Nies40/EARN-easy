# Authentication API contract

The frontend and FastAPI API share one origin. Use cookie authentication, not browser-stored JWTs. API request bodies are JSON; cookies are issued only by signup/login and cleared by logout or successful password reset.

Sources: `backend/app/modules/auth/router.py:48`, `backend/app/modules/auth/schemas.py:37`, and `backend/app/modules/dashboard/router.py:12`. Development also exposes interactive schemas at `/docs`.

## Account access

- Anonymous users may sign up, sign in, request password recovery, and submit verification/reset tokens.
- Unverified users may sign in, read their basic account through `GET /api/me`, resend verification, and sign out.
- `GET /api/dashboard` requires a session and verified email. It currently returns the verified user's public profile, not earnings or product data.
- `users.email_verified_at` is the source of truth. API responses expose the derived boolean `user.email_verified`.
- Unauthenticated protected requests return `401`; authenticated but unverified dashboard requests return `403`.

Access dependencies: `backend/app/api/dependencies.py:25`.

## Shared attempt limits

Signup, login, verification request/confirmation, and password forgot/reset POST endpoints have shared Redis-backed per-network limits, applied before body validation or database access. Successful, failed, and malformed attempts all count. Exhausted quotas return `429` with `Retry-After` in whole seconds. Redis failures return `503` with `Retry-After: 5`; the server does not silently disable protection. Logout, account reads, and dashboard reads do not depend on Redis.

The existing per-account email cooldowns remain independent of these quotas. The generic forgot-password response described below applies when the network quota is available; an exhausted client network receives the same `429` regardless of whether an email exists. See [rate limiting](RATE_LIMITING.md) for configuration and trusted-proxy requirements.

## Registration and sessions

`POST /api/signup` accepts `name`, `email`, and `password`, plus optional `username` and `phone`. It returns `201` with `message` and `user`, starts a session, and requests a verification email automatically. Passwords must have at least eight characters and no more than 72 UTF-8 bytes.

`POST /api/login` accepts `identifier` (email or username) and `password`. Both verified and unverified users may sign in. It returns `200` with `message` and `user` and rotates the caller's previous session.

`GET /api/me` returns `200` with `user` when signed in. Public user fields are `id`, `name`, `email`, `username`, `phone`, `email_verified`, and `created_at`; password hashes and tokens are never returned.

`POST /api/logout` is idempotent, revokes the current session, clears the cookie, and returns `200` with `message`.

## Email verification

### Request another verification email

`POST /api/email-verification/request` requires a session and no request body.

- Returns `202` with a generic `message` when delivery is requested.
- Already-verified accounts also receive `202`, but no message is sent.
- Requests within the per-account cooldown return `429` and `Retry-After` in seconds. The initial signup email counts toward the cooldown.
- A new token supersedes the previous verification token.

### Confirm email

`POST /api/email-verification/confirm` accepts:

```json
{"token": "<token from the email link>"}
```

It returns `200` with `message` on success. The token must be unexpired and unused. Invalid, expired, superseded, and already-used tokens return `400` with the same error. Verification does not sign the user in or replace an existing session. A current session immediately gains dashboard access after verification.

## Password recovery

### Request recovery

`POST /api/password/forgot` accepts:

```json
{"email": "user@example.com"}
```

It returns the same `202` status and `message` for known, unknown, and cooldown-limited accounts. This avoids disclosing account existence through the response body or status; it is not a constant-time guarantee. Emails are normalized. A valid request after the cooldown supersedes the previous reset token. Requesting a reset alone does not change the password or revoke sessions.

### Submit a new password

`POST /api/password/reset` accepts:

```json
{"token": "<token from the email link>", "password": "a-new-long-password"}
```

It returns `200` with `message` after atomically consuming the token, changing the bcrypt hash, and revoking every session belonging to that account. The response clears the caller's authentication cookie. No automatic login occurs; sign in again with the new password. Resetting a password does not mark email verified. Invalid or expired tokens return `400`; invalid passwords return `422` without consuming the token.

Transactions and row locking: `backend/app/modules/auth/service.py:118` and `backend/app/modules/auth/tokens.py:49`.

## Frontend handoff

The existing frontend does **not** implement the following screens yet:

- `/verify-email#token=...`: read the fragment token and show an explicit confirmation action that calls the verification confirmation API.
- `/reset-password#token=...`: read the fragment token, collect and confirm the new password, then call the reset API.
- Forgot-password and resend-verification controls.
- A dashboard screen using the verified-only dashboard endpoint.

Email links use `APP_URL`, never the incoming `Host` header. The token is in the URL fragment so browsers do not send it in HTTP paths or referrer headers. The frontend should remove the fragment with `history.replaceState` after reading it, keep the token only in memory, and submit it in the JSON body. Do not consume tokens on page load or through GET endpoints; email scanners and link previews must not change account state.

The link paths are reserved integration targets, not backend HTML pages. Until those screens exist, use `/docs` to exercise the API with tokens copied from Mailpit. No additional session-cookie access is needed in JavaScript.

Templates: `backend/app/modules/auth/emails.py:7`.

## Local email configuration

Run `docker compose up -d db mailpit redis` from the repository root, apply migrations, and start FastAPI as described in the [README](../README.md). Mailpit listens for SMTP on `localhost:1025`; its inbox is at <http://localhost:8025>. No domain, external credentials, or provider account is required. The API runs on the host, not inside Compose, so the default SMTP hostname is `localhost`.

Defaults are a 24-hour verification lifetime, a 30-minute reset lifetime, and a 60-second per-purpose email cooldown. All are configurable in `backend/.env.example`; settings are validated in `backend/app/core/config.py:38`.

If Mailpit/SMTP is unavailable but Redis is available, account creation still succeeds and the account remains limited. The background task logs a sanitized delivery error. Request a replacement after the cooldown once SMTP is available. A `202` response acknowledges the request, not successful delivery. In-process tasks are not durable and may be lost on restart; a persistent delivery queue and retries remain launch requirements.

Mailpit inboxes contain real bearer-token links. Keep them local and never expose the inbox or SMTP listener publicly. Do not log message bodies, SMTP credentials, reset/verification tokens, or request bodies containing passwords.

## Errors and tests

Errors use `{"error": "message"}`. Validation errors return `422` with an additional `details` list containing field names and messages, not submitted values (`backend/app/api/errors.py:7`). Tokens must be 43 URL-safe characters; structurally malformed tokens return `422`.

The isolated suite tests expiry, single use, replacement, cooldowns, access rules, SMTP settings/failures, and session revocation. Optional PostgreSQL tests exercise real row-lock behavior and concurrent verification, reset, resend, and login/reset requests. See [development checks](../README.md#development-checks).
