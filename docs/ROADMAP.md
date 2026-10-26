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

- [ ] Add real email delivery, verification links, resend flow, and verification enforcement.
- [ ] Add forgot-password and reset-password pages/API with expiring, single-use tokens.
- [ ] Revoke active sessions after password reset.
- [ ] Build a protected dashboard beyond the current account panel.
- [ ] Define which actions unverified users can access.

## Before public launch

- [ ] Add login/signup/recovery throttling, abuse protection, and a shared limiter for multiple workers.
- [ ] Apply request-size limits and trusted proxy rules at the deployment boundary.
- [ ] Schedule expired-session and expired-token cleanup.
- [ ] Add PostgreSQL integration tests to CI alongside the isolated test suite.
- [ ] Review database roles, production credentials/TLS, indexes, and connection limits.
- [ ] Configure HTTPS hosting, deployment migrations, backups, and a tested restore procedure.
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
