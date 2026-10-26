import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from app.db.permissions import DatabaseRoles, apply_runtime_grants, provision_roles
from app.ops.backup import BackupError, connect, create_backup, restore_test


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BackupError(f"Set {name} in a private operator environment file.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dedicated-database permissions and encrypted recovery tests."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "generate-secrets", help="Print fresh secrets; never prints existing credentials."
    )
    provision = commands.add_parser(
        "provision", help="Create new roles on an explicitly named dedicated database."
    )
    provision.add_argument("--database", required=True)
    provision.add_argument("--prefix", default="easyearn")
    provision.add_argument("--adopt-existing", action="store_true")
    grants = commands.add_parser(
        "apply-grants", help="Reconcile grants on roles created by this tool."
    )
    grants.add_argument("--database", required=True)
    grants.add_argument("--prefix", default="easyearn")
    backup = commands.add_parser(
        "backup", help="Create an encrypted backup without a plaintext dump file."
    )
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser(
        "restore-test", help="Verify restore into a disposable, newly generated target."
    )
    restore.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate-secrets":
            print(
                json.dumps(
                    {
                        name: secrets.token_urlsafe(48)
                        for name in (
                            "MIGRATOR_DATABASE_PASSWORD",
                            "API_DATABASE_PASSWORD",
                            "WORKER_DATABASE_PASSWORD",
                            "BACKUP_DATABASE_PASSWORD",
                            "BACKUP_ENCRYPTION_PASSPHRASE",
                        )
                    }
                )
            )
        elif args.command in ("provision", "apply-grants"):
            from app.db.permissions import assert_dedicated_database

            with connect(required("ADMIN_DATABASE_URL")) as db:
                roles = DatabaseRoles(args.prefix)
                if args.command == "provision":
                    passwords = {
                        kind: required(f"{kind.upper()}_DATABASE_PASSWORD")
                        for kind in ("migrator", "api", "worker", "backup")
                    }
                    result = provision_roles(
                        db, args.database, roles, passwords, adopt_existing=args.adopt_existing
                    )
                else:
                    assert_dedicated_database(db, args.database)
                    apply_runtime_grants(db, roles)
                    result = {"grants_applied": True}
            print(json.dumps(result))
        elif args.command == "backup":
            create_backup(
                required("BACKUP_DATABASE_URL"),
                args.output,
                required("BACKUP_ENCRYPTION_PASSPHRASE"),
            )
            print(json.dumps({"encrypted_backup_created": True}))
        else:
            print(
                json.dumps(
                    restore_test(
                        required("ADMIN_DATABASE_URL"),
                        args.input,
                        required("BACKUP_ENCRYPTION_PASSPHRASE"),
                    )
                )
            )
        return 0
    except Exception as error:
        # Do not expose DSNs, SQL, password verifiers, rows, or provider stderr.
        print(
            f"Database operation failed ({type(error).__name__}). "
            "Check configuration and the operations guide.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
