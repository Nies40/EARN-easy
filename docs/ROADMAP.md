# V1 roadmap

This translates the supplied Nies Technologies brief into implementation stages. FastAPI and PostgreSQL are the selected backend stack. Unchecked items are planned, not implemented.

## Foundation

- [x] Separate frontend assets from backend code.
- [x] Organize FastAPI into configuration, API, database, auth, and user modules.
- [x] Add PostgreSQL models and Alembic migrations.
- [x] Preserve signup/login and the signed-in account panel.
- [x] Support registration with name, email, and password; retain optional username/phone.
- [x] Add bcrypt hashing, unique identifiers, revocable cookie sessions, and logout.
- [x] Add isolated tests and local development configuration.

## Complete account features

- [x] Add SMTP delivery, verification links, resend flow, and backend verification enforcement.
- [x] Add forgot-password and reset-password APIs with expiring, single-use tokens.
- [x] Revoke all account sessions after password reset, including concurrent login sessions.
- [x] Add a verified-only dashboard API and limit unverified accounts to basic account access.
- [x] Add PostgreSQL concurrency tests for single use, cooldowns, and password-reset/login races.
- [ ] Build verification, recovery, and dashboard frontend screens using the API contract.

## Before public launch

- [x] Add shared Redis-backed attempt limits for login, signup, verification, and password recovery.
- [x] Test concurrent quotas, client-IP spoofing defenses, expiry, and fail-closed Redis outages.
- [ ] Tune quotas for real traffic and add monitoring/perimeter protection against distributed abuse.
- [ ] Replace best-effort background SMTP tasks with durable delivery and automatic retries.
- [ ] Apply request-size limits and trusted proxy rules at the deployment boundary.
- [ ] Schedule expired-session and expired-token cleanup.
- [ ] Add PostgreSQL integration tests to CI alongside the isolated test suite.
- [ ] Review database roles, production credentials/TLS, indexes, and connection limits.
- [ ] Configure HTTPS hosting, deployment migrations, backups, and a tested restore procedure.
- [ ] Register a domain, verify a production email sender, and select a suitable SMTP provider.
- [ ] Add privacy-conscious logging, monitoring, and operational alerts.
- [ ] Publish reviewed Terms of Service and Privacy Policy pages; decide how consent is recorded.
- [ ] Test accessibility and mobile layouts on real browsers/devices.
- [ ] Run a security review and confirm account enumeration and recovery behavior.

## Performance acceptance

- Target registration response time below two seconds under a defined expected load; measure it rather than assuming it.
- Define a measurable login latency target instead of promising “instant” login.
- Load-test realistic concurrent registrations and logins, including bcrypt CPU cost and database pool limits.
- Send email through a reliable background-delivery mechanism without claiming verification before delivery or completion.
- Keep security checks in place when optimizing latency.

## Outside V1

- Payments and withdrawal flows.
- Admin product sales.
- Chat.

No earnings, commission, referral, or product-selling implementation is included in this structural pass.
