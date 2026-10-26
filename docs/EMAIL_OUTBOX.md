# Durable email delivery and operations

Account emails are saved in PostgreSQL in the same transaction as their account/token changes, encrypted with authenticated Fernet encryption, and delivered by a separate Python process. No SMTP call runs in an API request. Redis remains a rate-limiter store, not an email queue.

Sources: `backend/app/modules/outbox/service.py:14`, `backend/app/modules/outbox/models.py:19`, `backend/app/modules/outbox/worker.py:44`, and `backend/app/workers/email.py:20`.

## Required setup

Run from `backend/` after installing dependencies:

```bash
uv run python -m app.workers.email --generate-key
```

This prints a **new secret JSON key ring**. Put that array in `EMAIL_OUTBOX_KEYS` in `backend/.env` and supply the same ring to the API and worker. Never commit it, paste it into an issue, or regenerate it on restart. Protect the real environment file with owner-only permissions and use a secret manager in production. There is no fallback key: the API and worker refuse startup with an empty ring. Key generation, status, and cleanup do not need a decryption key.

Apply migration `0003` before deploying the new API:

```bash
uv run alembic upgrade head
```

Start the API as described in the [README](../README.md), then run a worker in another terminal:

```bash
uv run python -m app.workers.email
```

Use a process supervisor for production. Keep the worker running and alert on its absence. The default loop polls once per second when idle and performs a bounded cleanup batch at startup and every five minutes. SIGINT/SIGTERM request graceful shutdown after the current operation; a forced exit is recoverable through leases. No domain or SMTP-provider account is needed with local Mailpit.

## Queue lifecycle

- `pending`: encrypted payload retained; waiting for `next_attempt_at`.
- `processing`: a committed claim records an attempt, random lease ID, and expiry.
- `sent`: SMTP accepted the message; ciphertext removed. This is not proof of inbox delivery.
- `failed`: permanent failure, invalid authenticated payload, or exhausted attempts; ciphertext removed.
- `discarded`: expired/consumed/superseded token or changed recipient; ciphertext removed.

Database constraints enforce terminal payload removal and valid lease state. User deletion cascades to jobs. Job metadata stores a user UUID, purpose, token hash, key fingerprint, timestamps, and constant error codes—not plaintext recipients or token links. Ciphertexts are cryptographically bound to their job UUID, user, purpose, and token hash.

Clearing a live payload column is logical deletion, not a forensic disk wipe. Database logs and backups can retain older ciphertext; define key and backup-retention policies accordingly.

Workers use `FOR UPDATE SKIP LOCKED` to claim distinct due jobs. A crashed worker's processing claim becomes eligible again after its lease expires. A random lease ID prevents an obsolete claimant from sending or acknowledging a replacement claim. During SMTP the worker holds only the job-row lock, not user/token locks; another worker skips that job even if its lease expires, and auth/resend transactions are not blocked by a slow SMTP server.

Leases do not forcibly break PostgreSQL locks. Configure database connection keepalives and appropriate idle-transaction timeouts for network partitions, and size supervision/shutdown deadlines around SMTP timeouts. A disconnected host whose database connection has not yet been detected can delay recovery beyond the lease interval.

The worker checks account, token expiry/usage, and recipient before sending. If a token is superseded or consumed while SMTP is already in flight, an obsolete email can still arrive, but its token cannot be used. Future email-change functionality must explicitly revoke old tokens as well; queue checks do not replace that account-security rule.

SMTP acceptance and database acknowledgment cannot be atomic. A crash after acceptance but before commit can send the message again after recovery. Delivery is **at-least-once, not exactly-once**, with a stable persisted `Message-ID` per job. Single-use authentication tokens prevent duplicate emails from granting extra access.

## Retries and key rotation

Transient SMTP/network failures retry with exponential backoff and bounded random jitter. Permanent recipient/content failures stop immediately; SMTP authentication failures retry to allow configuration recovery, but still have bounded attempts. Error text, payloads, credentials, and recipient addresses are never logged by the worker. Logs identify job UUIDs and constant error codes only.

Defaults in `backend/app/core/config.py:63`:

- `EMAIL_OUTBOX_KEYS=[]`: required secret ring; first key encrypts new jobs, all keys can decrypt.
- `EMAIL_WORKER_POLL_SECONDS=1`: idle polling interval.
- `EMAIL_WORKER_LEASE_SECONDS=120`: crashed-claim recovery interval.
- `EMAIL_WORKER_MAX_ATTEMPTS=5`: maximum claims that can attempt SMTP; interrupted claims count.
- `EMAIL_RETRY_BASE_SECONDS=30`, `EMAIL_RETRY_MAX_SECONDS=3600`: backoff bounds.
- `EMAIL_CLEANUP_INTERVAL_SECONDS=300`, `EMAIL_CLEANUP_BATCH_SIZE=500`: maintenance cadence and per-table batch cap.
- `EMAIL_OUTBOX_RETENTION_SECONDS=604800`: retain terminal metadata for seven days.

A missing key fingerprint pauses that job with `key_unavailable` without consuming attempts or deleting its ciphertext. Restore the proper ring before the token expires. Corrupted ciphertext for a known key is permanently failed and removed. Expired jobs are removed from delivery even if their key is unavailable. Lost keys cannot be reconstructed from PostgreSQL.

Rotate safely:

1. Generate a fresh key and deploy a ring containing new and old keys to **all delivery workers** first.
1. Deploy the same ring to all API processes, with the new key first.
1. Inspect `--status`: `active_key_ids` shows non-secret SHA-256 key fingerprints still used by active jobs. Wait until old-key active jobs are gone before removing old keys from running processes.
1. Retain protected old keys separately for as long as backup recovery requires them. Do not discard keys needed to decrypt active jobs in a restore.

Never run old/new environments against the same real-user database with incompatible key rings. Restarting only the API or worker does not lose queued jobs. Never roll back migration `0003` without draining or safely backing up jobs and preserving their keys.

## Monitoring and maintenance

From `backend/`:

```bash
uv run python -m app.workers.email --status
uv run python -m app.workers.email --once
uv run python -m app.workers.email --cleanup
```

`--status` prints aggregate state counts, constant error-code counts, oldest pending time, active key fingerprints, and expired-lease count. It does not decrypt or display email contents. Alert on failed jobs, `key_unavailable`, growing queue age, expired leases, missing workers, and database/SMTP errors. Protect access to database credentials; no public queue-inspection endpoint exists.

`--once` handles at most one due job, including a discard/failure transition; an empty queue exits normally. Failed jobs cannot be replayed because their payloads have been erased. After fixing the underlying issue, users request a fresh verification/reset email subject to the normal cooldown.

Cleanup removes expired sessions, old used/expired auth tokens, expired active job payloads, and terminal metadata beyond retention. It preserves recent token rows needed for email cooldowns and skips rows locked by other workers. Batches are bounded: tune worker count/cadence/batch size for traffic. Run `--cleanup` through a scheduler too if delivery workers will be offline for extended periods.

SQL errors retry during the continuous worker loop and emit sanitized class names, not SQL payload parameters. A database transaction failure cannot persist a partial account/token/job creation. After a backup restore, invalidate sessions/auth tokens and discard stale active mail jobs before reopening traffic; test restoration and key recovery as part of deployment preparation.

## Tests and release status

The isolated suite tests encryption, metadata binding, key redaction/rotation, transactional rollback, retries, permanent failures, expired/stale links, terminal scrubbing, lease recovery, and cooldown-preserving cleanup. PostgreSQL integration tests exercise competing workers, crashed delivery recovery, and slow SMTP without blocking account requests. See [development checks](../README.md#development-checks).

This is not a complete production deployment. Passing required hosted [CI checks](CI.md), least-privilege roles, tested backups, secret management, SMTP sender verification, delivery/bounce monitoring, perimeter limits, supervised services, load testing, and an independent security review remain required before public launch.
