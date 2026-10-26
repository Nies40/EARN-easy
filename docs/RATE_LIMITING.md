# Authentication rate limiting

Authentication attempt quotas use Redis and apply across all FastAPI workers. The backend uses no in-memory fallback, and no domain or external provider is needed locally. PostgreSQL remains the store for users, sessions, verification tokens, and password resets; Redis stores only expiring counters.

Sources: `backend/app/api/rate_limit.py:30`, `backend/app/core/rate_limit.py:63`, and `backend/app/core/config.py:48`.

## Default quotas

Each endpoint has a separate quota per client network within a 60-second fixed window:

- `POST /api/signup`: **5** attempts, configured by `AUTH_RATE_LIMIT_SIGNUP`.
- `POST /api/login`: **10** attempts, configured by `AUTH_RATE_LIMIT_LOGIN`.
- `POST /api/email-verification/request`: **5** attempts, configured by `AUTH_RATE_LIMIT_VERIFICATION_REQUEST`.
- `POST /api/email-verification/confirm`: **20** attempts, configured by `AUTH_RATE_LIMIT_VERIFICATION_CONFIRM`.
- `POST /api/password/forgot`: **5** attempts, configured by `AUTH_RATE_LIMIT_PASSWORD_FORGOT`.
- `POST /api/password/reset`: **10** attempts, configured by `AUTH_RATE_LIMIT_PASSWORD_RESET`.

`AUTH_RATE_LIMIT_WINDOW_SECONDS` controls the common window length. Every worker must use the same quota settings, Redis database, `AUTH_RATE_LIMIT_KEY_PREFIX`, and `APP_ENV`.

All attempts count, including successes, incorrect credentials, malformed JSON, and validation failures. The limiter runs before request-body parsing, database access, and password hashing. Existing per-account email cooldowns still apply after the network quota check; this does not introduce global account lockouts that another IP could deliberately trigger.

IPv4 addresses are canonicalized, IPv4-mapped IPv6 addresses use the IPv4 bucket, and ordinary IPv6 addresses share a `/64` bucket to prevent trivial address rotation. Clients behind a shared NAT or IPv6 subnet share quotas; tune limits for expected traffic rather than treating the defaults as universal production thresholds. Encoded URLs, trailing-slash redirects, and ASGI root paths cannot skip the quota for a protected route.

## Responses and failure policy

An exhausted quota returns `429` with:

```json
{"error": "Too many requests. Please try again later."}
```

`Retry-After` is the remaining Redis TTL rounded up to at least one second. A Lua script increments the counter and sets its expiry atomically. Windows begin with the first attempt; subsequent allowed or rejected attempts do not extend the expiry. This is not a sliding-window limiter, so bursts near window boundaries are still possible.

Redis connection, timeout, pool-exhaustion, protocol, or invalid-response failures return `503`, `Retry-After: 5`, and:

```json
{"error": "Authentication is temporarily unavailable. Please try again."}
```

Both rejection responses have `Cache-Control: no-store`. They do not expose Redis details or submitted credentials. Missing or invalid server-provided client addresses also fail closed. Successful Redis checks are required even in development; there is no environment flag that silently disables protection.

Logout, `/api/me`, dashboard reads, static files, and API documentation do not require Redis. `/api/health` retains its database-connectivity contract; it is not a complete Redis readiness probe. Monitor Redis separately, including the Compose service's health check.

## Local setup and configuration

From the repository root:

```bash
docker compose up -d db mailpit redis
```

Start the backend using the [README](../README.md). For an existing setup, install the updated lockfile with `uv sync --locked` in `backend/` and start Redis. No database migration is added by this feature.

Defaults in `backend/.env.example`:

- `REDIS_URL=redis://localhost:6379/0`: shared Redis endpoint and database.
- `REDIS_TIMEOUT_SECONDS=0.5`: each pool-wait, connect, and socket timeout. Automatic network retries are disabled, avoiding unbounded outage delays; the timeout is not a single total-request deadline.
- `REDIS_MAX_CONNECTIONS=20`: maximum Redis connections per app process. Pool waits are bounded by the configured timeout.
- `AUTH_RATE_LIMIT_KEY_PREFIX=easyearn:auth-limits`: namespace; `APP_ENV`, endpoint name, and a SHA-256 digest of the canonical client network are appended.
- `AUTH_RATE_LIMIT_WINDOW_SECONDS=60`: quota lifetime in seconds.

`REDIS_URL` accepts `redis://` or `rediss://`, optional credentials, and a nonnegative database number. URL query parameters are rejected so they cannot override the configured timeouts or disable TLS checks. `rediss://` connections explicitly require certificate and hostname verification. Redis credentials use a redacted settings field; never log connection URLs. Use private networking, authentication, and TLS for production remote Redis. The service must permit the Lua/counter operations used here, including `EVAL`, `INCR`, `PTTL`, and `PEXPIRE`.

Compose exposes Redis only on `127.0.0.1:6379`, with no persistence. Restarting Redis clears its counters, not PostgreSQL account data; restarting only FastAPI leaves shared counters intact while Redis stays running. Evicting keys also resets their quotas, so plan production capacity and eviction policy deliberately. No application code runs a Redis database flush.

Network digests keep raw addresses out of counter keys but are **not anonymization**. Limiter logs omit client addresses, passwords, tokens, request bodies, and Redis URLs; application-server and proxy access logs require their own privacy and retention policy.

## Client addresses and trusted proxies

The app reads the ASGI client address and does not interpret `X-Forwarded-For`, `X-Real-IP`, or `Forwarded` headers itself. For direct/local access, explicitly disable application-server proxy processing:

```bash
uv run uvicorn app.main:app --reload --no-proxy-headers
```

Uvicorn can rewrite the ASGI client address before requests reach the app. Behind a real reverse proxy, enable that processing only for the actual proxy addresses. For example, **only when the sole proxy runs on the same host at `127.0.0.1`**:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

The proxy must set trusted client/protocol headers itself rather than accepting spoofed values from callers. Keep the backend inaccessible directly from the public network, never use `--forwarded-allow-ips='*'`, and adapt the allowlist to your actual deployment. If proxy processing stays disabled behind a shared proxy, all callers appear as that proxy and share one quota. Same-domain frontend/API hosting does not remove this requirement.

## Tests

Run the isolated suite in `backend/` with `uv run pytest -q`. It injects a Redis test double and tests endpoint coverage, threshold boundaries, headers, outage behavior, malformed bodies, privacy, IP normalization, URL variants, and proxy-header spoofing. It also tests an actual refused local TCP connection without contacting an external service.

Live Redis-compatible integration tests run only when explicitly configured:

```bash
TEST_REDIS_URL=redis://localhost:6379/0 uv run pytest -m redis -q
```

They exercise shared quotas across independent application instances, atomic concurrent admission, expiry without extension, and repair of counters missing an expiry. Each test uses a unique prefix; keys expire within ten seconds, and cleanup never flushes a database. Use a development/test instance, never production Redis.

## Remaining launch work

Rate limiting is one abuse-control layer, not complete DDoS protection or a defense against all distributed credential attacks. Add deployment request-size/concurrency limits, traffic monitoring, appropriately tuned quotas, and perimeter protection. Durable email delivery/retries, expired-record cleanup, backups, and the other [launch requirements](ROADMAP.md) remain pending.
