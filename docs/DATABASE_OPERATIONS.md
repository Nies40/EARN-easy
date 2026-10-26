# Database permissions, backups, and recovery drills

These are explicit operator commands, not HTTP endpoints. They do not modify an existing database automatically. Production API and worker startup now reject privileged database accounts. Local Compose still provides a development/bootstrap administrator; its default password is not suitable for production.

Sources: `backend/app/db/permissions.py:1`, `backend/app/ops/database.py:1`, `backend/app/ops/backup.py:1`, and `backend/migrations/env.py:1`.

## Role boundaries

For a role prefix of `easyearn`, provisioning creates:

- `easyearn_owner`: **NOLOGIN**, owns application tables, permits controlled DDL in `public`.
- `easyearn_migrator`: login, no inherited owner privileges; Alembic explicitly assumes the owner role.
- `easyearn_api`: user/auth DML needed by the API, no user deletion or schema changes. Outbox access is insert plus `id`/`created_at` reads for ORM defaults, not ciphertext reads or delivery-state updates.
- `easyearn_worker`: job processing/cleanup, token/session cleanup, and only user `id`, `email`, and `email_verified_at` reads. It cannot read password hashes or modify users.
- `easyearn_backup`: read-only data access for logical backups, no writes or DDL.

Runtime roles have no superuser, create-role, create-database, replication, RLS-bypass, database-temp/create, schema-create, ownership, or role-membership privileges. When `APP_ENV=production`, startup checks fail if these restrictions or required grants are not met. Checks occur at startup; monitor subsequent administrative privilege changes too.

The worker receives update permission only on `created_at` metadata in auth/session tables because PostgreSQL requires an update privilege for row locking. It can delete auth/session rows for maintenance. These are process-level privileges, not row-level-security guarantees; backend code remains responsible for filtering cleanup and authorizing user operations.

PostgreSQL roles are cluster-wide and grants are additive. Use unique prefixes per environment. This tool only changes the explicitly named database; it does not deny connections to other databases that still grant `CONNECT` through `PUBLIC`. Enforce isolation through provider/`pg_hba.conf` rules or a dedicated cluster. Never share production roles, keys, or databases with development.

## Private environments and provisioning

Use a dedicated PostgreSQL database. The tool refuses maintenance databases, unrelated user tables/views/sequences/functions, mismatched table shapes, and existing role names. It never rotates an existing password implicitly. Extensions and managed-service restrictions require administrator review.

Copy the `.env.admin.example`, `.env.migrations.example`, `.env.worker.example`, and `.env.backup.example` templates to their corresponding private files. Set owner-only permissions. For local development, from `backend/`:

```bash
cp .env.admin.example .env.admin
cp .env.migrations.example .env.migrations
cp .env.worker.example .env.worker
cp .env.backup.example .env.backup
chmod 600 .env .env.admin .env.migrations .env.worker .env.backup
uv run python -m app.ops.database generate-secrets
```

The final command prints **fresh secrets only**. Put the four distinct database passwords in the administrator file and relevant connection URLs; put the separate backup passphrase in the backup file. Do not reuse `EMAIL_OUTBOX_KEYS` as a backup passphrase. Keep outbox keys recoverable through a separate secret-management process.

For a **new, empty, dedicated** database named `easyearn`:

```bash
uv run --env-file .env.admin python -m app.ops.database provision --database easyearn --prefix easyearn
uv run --env-file .env.migrations alembic upgrade head
```

The administrator must be authorized to create roles, manage database/schema grants, and change ownership. The entire provisioning transaction rolls back on failure. Passwords are converted to SCRAM verifiers client-side, rather than inserting plaintext passwords into DDL statements. Database statement logs can still contain sensitive verifiers; protect logs.

For an existing application database, first take and verify a pre-change backup using your current provider/administrator backup process. Plan a maintenance window and prepare the new runtime credentials. Provisioning requires an explicit `--adopt-existing` flag and changes ownership only for recognized application tables. It revokes public database/schema access and reconciles table/column grants; never use it on a shared database. The new read-only backup role does not exist until provisioning succeeds, so it cannot supply your initial pre-adoption backup.

After provisioning, change the API's `.env` `DATABASE_URL` to the API login, not the bootstrap administrator. Put the worker login in `.env.worker`; put the migrator login and `DATABASE_ROLE_PREFIX` in `.env.migrations`. Keep the same canonical `APP_URL` and outbox key ring in API/worker configurations. In production configure each process's HTTPS/SMTP/TLS settings explicitly.

```bash
uv run uvicorn app.main:app --reload --no-proxy-headers
uv run --env-file .env.worker python -m app.workers.email
```

`EASYEARN_ENV_FILE` selects a private settings file instead of silently reading the API's `.env`. Template worker/migration files set it themselves. Process environment values take precedence. Restart processes after changing credentials or key rings. In production, use separate service identities/secret mounts: **do not mount administrator, backup, or migration secrets into API/worker containers**. Git/Docker ignores help prevent accidental packaging but are not an access-control boundary.

Migrations with `DATABASE_ROLE_PREFIX` explicitly `SET ROLE` to that prefix's owner, then apply the reviewed grants in code after migration. New feature tables require an explicit privilege-policy update; no broad runtime default grants are added. To reconcile existing managed roles manually:

```bash
uv run --env-file .env.admin python -m app.ops.database apply-grants --database easyearn --prefix easyearn
```

Do not put `DATABASE_ROLE_PREFIX` in runtime environments. Protect migration credentials and review migration/permission changes as privileged code.

## Encrypted logical backups

The operator host needs PostgreSQL `pg_dump`/`pg_restore` compatible with the server and GnuPG 2 (`gpg`, `gpgconf`). These POSIX commands use file descriptors and filesystem permissions and are intended for Linux/Unix, not native Windows. Use trusted binaries; `PG_BIN_DIR` can point to a trusted matching client directory.

Set `BACKUP_DATABASE_URL` to the read-only backup login and `BACKUP_ENCRYPTION_PASSPHRASE` to a separately stored generated secret of 32–256 bytes. Placeholder passphrases are rejected. DSNs need explicit host, database, and user; service profiles and inline client-key passphrases are intentionally unsupported. Use authenticated TLS (`sslmode=verify-full` and trusted certificates) for remote production connections.

```bash
mkdir -m 700 backups
uv run --env-file .env.backup python -m app.ops.database backup --output backups/snapshot.dump.gpg
```

The tool streams PostgreSQL's custom archive directly into GnuPG AES-256 encryption; it never creates a plaintext dump file. It uses an isolated GnuPG home, a passphrase file descriptor instead of an argument, and no symmetric passphrase cache. Connection passwords are kept out of subprocess arguments, and unrelated credentials are stripped from PostgreSQL-tool environments. Provider stderr and database rows are not printed.

Outputs must end in `.dump.gpg`, use an existing owner-only directory, and never overwrite another path. A private partial file is published atomically only after both pipeline stages succeed; the final encrypted file is owner-read-only. Ignore rules exclude backup artifacts. Failed/interrupted runs can leave private partial files; inspect them rather than treating them as completed backups.

Backups and rehearsals require this release's expected tables/columns and migration head. For a pre-upgrade backup, use the currently deployed matching release before changing schema. This is a logical app-database backup, not a roles/configuration/WAL/PITR backup. It does not include outbox encryption keys, TLS/SMTP secrets, PostgreSQL globals, or host configuration.

Choose and document backup frequency, RPO/RTO, retention, off-site/immutable storage, and a separate key-recovery process. Scheduling/uploading/deleting retained backups is not automated by this command. A backup on the same host alone is not a disaster-recovery strategy.

## Non-destructive restore rehearsals

For a rehearsal only, provide `ADMIN_DATABASE_URL` in a private restore environment and the backup passphrase. Never expose this environment to the API. For example, after preparing a private `.env.restore` containing those two values:

```bash
uv run --env-file .env.restore python -m app.ops.database restore-test --input backups/snapshot.dump.gpg
```

The tool authenticates the complete encrypted archive before creating a target. It then generates an isolated `easyearn_restore_test_<uuid>` database and a fresh non-superuser owner, runs `pg_restore --no-owner --no-acl` there, validates schema/row counts, and deletes that temporary database/role. **There is no option to target an existing database or activate a production restore.** Source accounts, sessions, and encrypted jobs are unchanged.

Restored sessions and verification/reset tokens are deleted, active mail jobs discarded, and password hashes replaced with an unknown random password before cleanup. This demonstrates a recovery policy that does not resurrect old sessions, reset links, or pre-reset passwords. Reported counts describe restored data before sanitization. Automated tests also decrypt a restored outbox message with the separate key ring before sanitization; the operator command itself does not display mail or keys.

Only restore archives you trust. Database archives contain executable SQL; integrity checks and a limited temporary role are defense layers, not a promise that arbitrary malicious archives are harmless. Wrong passphrases/corrupt data fail without changing the source. A forced operator-process kill can leave a generated temporary role/database: inspect matching names and active connections before an administrator removes a confirmed rehearsal artifact. No broad automatic database/role deletion is performed.

Actual disaster activation requires a separate, approved runbook: isolate traffic, restore into a new environment, apply the appropriate reviewed migrations/roles, invalidate authentication and require recovery, verify keys/configuration, test functions, then explicitly cut traffic over. Do not improvise an in-place restore on a live database.

## Verification and CI

The isolated suite tests filename/permission/secret guards, credential redaction, environment isolation, and SQL-safe role names. Live role/recovery tests require an **explicit administrator URL for a disposable test cluster**, never production:

```bash
TEST_DATABASE_ADMIN_URL=postgresql://test_admin:test_password@localhost:5432/postgres \
  uv run pytest -m dbops -q
```

They create unique databases/roles, run real Alembic migrations as the migrator, exercise API/worker operations as restricted roles, prove forbidden operations fail, preserve existing credentials, and perform encrypted backup/restore/key-recovery checks. Sources remain unchanged. CI configures these tests against disposable services and uses client tools from the matching PostgreSQL container; local tooling and the hosted workflow still need their own successful validation.

Production remains dependent on least-privilege deployment, strong administrator secrets, TLS/network isolation, monitored schedules/off-site storage, repeated recovery drills, and human review. Passing a rehearsal is not proof of a complete disaster-recovery plan or absolute security.
