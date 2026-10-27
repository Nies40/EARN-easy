# Backend acceptance and handoff

## Current disposition

**Core backend implementation: ready for frontend integration. Public-release sign-off: conditional, not complete.**

The FastAPI/PostgreSQL authentication foundation, verified-account gate, encrypted mail outbox, worker, rate limits, request-size guards, permissions, and recovery tools are implemented. This document separates tested local evidence from external acceptance requirements. It is not a claim of absolute security or unlimited capacity.

The repeatable runner is `backend/app/ops/acceptance.py:1`; it uses actual Uvicorn HTTP, PostgreSQL, Redis, SMTP, and a separate worker process, not mocked transport or the fast bcrypt test fixture.

## Verified locally

- Fresh generated database/roles, private per-process environments, migrations, schema-drift check, and runtime privilege audits.
- Signup with name/email/password, duplicate-email rejection, limited account access, and verified-only dashboard access.
- A verification email delivered through a standalone CLI worker and local SMTP; verification is single-use.
- Forgot-password responses consistent for known/unknown emails; reset email delivered by another worker process.
- Password reset revokes the old session, rejects the old password, preserves email verification, and permits a new login/logout cycle.
- The real API stores bcrypt cost-12 hashes. Worker jobs complete with ciphertext scrubbed.
- Oversized API requests receive `413`; IP quotas remain enabled.
- Existing tests separately cover production cookie flags, restricted SQL grants, concurrency, encrypted backups/recovery, and failure handling.

The local runner creates and drops only generated test databases and roles. It does not alter an existing application database. Test messages stay in a loopback SMTP sink; no external emails are sent.

## Repeatable acceptance command

Install development dependencies with `uv sync --locked` inside `backend/`. Use an isolated local PostgreSQL test cluster and Redis instance, then prepare `.env.acceptance` from `.env.acceptance.example`. Never use production/shared live services.

```bash
cp .env.acceptance.example .env.acceptance
chmod 600 .env.acceptance
uv run --env-file .env.acceptance python -m app.ops.acceptance --confirm-disposable-cluster
```

Administrator credentials are used only by the controller to create/remove fresh resources. API, worker, and migration children receive only their own generated environments; they cannot inherit the administrator/application credentials from your shell. Missing child profiles fail instead of falling back to application defaults. Remote test targets are refused.

The test covers bootstrap against a fresh database and the locked development environment, not a claim that every teammate or supported Python version has completed an independent fresh install. The configured hosted CI matrix must still run successfully.

## Performance baseline and limits

Recorded evidence: [local baseline JSON](acceptance/local-baseline-2026-10-27.json). Measurements used Python 3.14.8, eight logical CPUs, PostgreSQL 18.6, a live Valkey 9.1.2 Redis-compatible server, one local Uvicorn process, 10,000 seeded accounts plus a functional probe account, and 100 requests per operation. bcrypt stayed at cost 12.

| Concurrent requests | Registration p95 | Login p95 | Result against local thresholds |
| ------------------- | ---------------- | --------- | ------------------------------- |
| 5                   | 0.2925 s         | 0.3013 s  | Pass                            |
| 10                  | 0.4790 s         | 0.4845 s  | Pass                            |
| 20                  | 1.1215 s         | 1.1536 s  | Fail: provisional login target  |

All sampled registrations completed below two seconds, and every measured request returned its expected success status. The runner checks registration p95 below two seconds and a **provisional** login p95 below one second; the original “instant login” requirement needs stakeholder agreement on a measurable SLO. The twenty-concurrent profile is retained as failed, not reclassified after relaxing a threshold.

This is a closed-loop local batch, not thousands of simultaneous registrations, a sustained load/soak test, or a production capacity guarantee. Timings include each HTTP connection/request/response but exclude client construction. Registration measures durable queueing; the delivery worker is idle during timed batches. Client requests bind distinct real loopback IPs so normal per-network quotas remain enabled, without accepting spoofed forwarded headers. Shared-NAT quota tuning still needs real traffic assumptions.

Run your own baseline, without changing production security settings:

```bash
uv run --env-file .env.acceptance python -m app.ops.acceptance \
  --confirm-disposable-cluster --benchmark --seed-users 10000 \
  --requests 100 --concurrency 5 --output acceptance-results.json
```

Reports contain aggregate metrics, not URLs, passwords, tokens, or email contents. The output file must be new. Exit `0` means requested checks passed, `1` means a latency/status threshold failed, and `2` means configuration/execution did not complete. Keep failed reports too. The runner caps concurrency at 64 and requests per operation at 1000, and refuses to use `DATABASE_URL` as an implicit test target.

## Frontend handoff

Use the [authentication contract](AUTHENTICATION.md), development `/docs`, and [README](../README.md). Frontend/API share one origin; use cookies with same-origin requests, never browser-stored JWTs.

Frontend owners still need to connect/build:

- Verification and reset pages at `/verify-email#token=...` and `/reset-password#token=...`, using explicit JSON POST actions.
- Forgot-password/resend controls and dashboard rendering; `/api/me` exposes `email_verified` for limited/verified UI states.
- User-facing handling of `401`, `403`, `422`, `429`/`Retry-After`, `503`, and request-size errors.
- Real-browser mobile/accessibility checks and the joint end-to-end acceptance walkthrough.

The current dashboard API returns the verified profile, not earnings, commissions, payments, product sales, or chat. Those business features are not silently included in this milestone.

## External sign-off items

1. **Hosted CI:** the read-only GitHub check on 2026-10-27 found no runs for `backend`, and `backend.yml` was not available through the default-branch workflow lookup. A maintainer must get the workflow registered/enabled and verify the Python 3.12–3.14 jobs, then require them through branch protection. No push, dispatch, or repository-settings change was made by this work.
1. **Capacity agreement:** agree peak concurrency/RPS, login latency SLO, shared-network quotas, and availability/error budgets. Validate the chosen deployment with TLS/network overhead and representative worker/traffic load. The local twenty-concurrent login result does not meet the provisional one-second target.
1. **Staging integration:** frontend owner and backend owner exercise the actual UI against staged APIs. Local SMTP checks do not verify a production provider, sender/domain policy, DNS, or delivery/bounce handling.
1. **Operations/security:** provision real restricted roles and secrets, verify TLS/proxy/network boundaries, supervise services, monitor alerts, configure off-site backup schedules/retention, rehearse restoration in the deployment environment, and perform an independent security review.

Backend coding and local verification can be handed off now. Formal acceptance of these shared/external items requires the responsible people and environment; it cannot be inferred from passing unit tests or a clean advisory scan.
