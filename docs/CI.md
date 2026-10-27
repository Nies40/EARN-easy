# Backend checks and dependency security

The GitHub Actions workflow in `.github/workflows/backend.yml:1` checks every push and pull request, with a manual trigger available too. It does not deploy the application or require production secrets. The hosted workflow will run after the changes are pushed and Actions is enabled; local validation is not a substitute for that first run.

## Checks

Each Python 3.12, 3.13, and 3.14 job uses its own disposable PostgreSQL 17 and Redis 7 services and runs:

- `uv sync --locked` to enforce the committed lockfile.
- Ruff lint checks.
- Alembic upgrades and model/schema-drift checks.
- The complete isolated, PostgreSQL, and Redis integration test suite.
- Fresh-database acceptance using real Uvicorn HTTP, local SMTP, and separate worker processes.
- The worker's aggregate status command.
- Outbox migration downgrade/upgrade checks against the disposable database only.
- Restricted API/worker/backup grants and encrypted restore rehearsals in fresh temporary databases.
- A strict advisory audit of the hashed, pinned runtime dependencies exported from `uv.lock`.

The workflow generates and masks a fresh Fernet key for its own job. Tests also generate their own temporary keys and schemas. The service password in the workflow is an ephemeral test credential, never a production credential. Tests do not send external email.

Performance thresholds are intentionally not CI gates on variable shared runners. Run the isolated opt-in baseline and review the measured results in [backend handoff](BACKEND_HANDOFF.md), including the retained high-concurrency failure and pending staging/capacity agreement.

`TEST_DATABASE_ADMIN_URL` is used only for temporary role/database tests in that disposable service. `PG_BIN_DIR` points to CI wrappers that run the service container's matching `pg_dump`/`pg_restore`, with passwords forwarded through environment variables rather than command arguments. GnuPG runs on the runner host. No production backup or administrator account is used.

## Workflow security

- Actions are pinned to verified full commit SHAs, not moving branch references.
- The repository token has only `contents: read`; checkout does not persist it.
- Untrusted PR code runs through `pull_request`, never `pull_request_target` with privileged secrets.
- Jobs use GitHub-hosted Ubuntu runners, bounded job timeouts, and per-branch cancellation of superseded runs.
- No production database, Redis, SMTP, or encryption secrets are referenced.
- No path filters are used, so documentation-only PRs can still satisfy required status checks.

After the first hosted run, configure branch protection to require the three Python jobs and trusted reviews for workflow/dependency changes. This repository setting is not changed automatically. Pin updates must be reviewed against the official publishers; keep the pinned uv version compatible with the committed lockfile.

Repository-wide formatting is not currently a CI gate because existing formatting differences predate this workflow. Ruff lint remains mandatory; formatting cleanup should be a separate change rather than silently rewriting unrelated files.

## Run the advisory audit locally

From `backend/` after `uv sync --locked`, on Linux:

```bash
set -o pipefail
uv export --locked --no-dev --no-emit-project --no-header --no-annotate --format requirements.txt \
  | uv run pip-audit --strict --require-hashes --disable-pip --progress-spinner off --requirement /dev/stdin
```

The export includes all locked runtime dependencies and their hashes, not just top-level requirements. The audit does not resolve or install replacement dependencies. It queries published advisory data; network or collection failures fail the strict check. Do not bypass the gate with ignored vulnerabilities without a documented risk decision.

The initial audit flagged published advisories in `cryptography` 48.0.1. The minimum is now 50.0.2, with the fixed release locked in `backend/uv.lock`; encryption and authentication regression tests must pass after such upgrades. This does not imply those older vulnerable library APIs were exposed through the application's Fernet usage.

Run the workflow manually before a release when no code changes have occurred, so newly published advisories can still be checked. This is not continuous production monitoring. Python advisory scans do not cover operating-system/container vulnerabilities, deployment configuration, business logic, unknown vulnerabilities, or every transitive native library. Independent security review, updates, monitoring, and tested backups remain necessary.
