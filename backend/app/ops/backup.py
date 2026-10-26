import os
import secrets
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import bcrypt
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.db.permissions import ALL_TABLES, assert_dedicated_database, validate_application_schema


class BackupError(ValueError):
    pass


def libpq_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def connection_parameters(value: str) -> dict:
    params = conninfo_to_dict(libpq_url(value))
    if not all(params.get(name) for name in ("host", "dbname", "user")) or "service" in params:
        raise BackupError(
            "Use an explicit PostgreSQL host, database, and user, not a service profile."
        )
    if "sslpassword" in params:
        raise BackupError("Inline client-key passphrases are not supported by backup subprocesses.")
    return params


def connect(value: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        make_conninfo(**connection_parameters(value)), autocommit=autocommit, connect_timeout=5
    )


def pg_command(tool: str, url: str, *, database: str | None = None) -> tuple[list[str], dict]:
    params = connection_parameters(url)
    env = dict(os.environ)
    # Explicit credentials only; do not inherit unrelated libpq credentials/options.
    for key in tuple(env):
        if (
            key.startswith("PG")
            or any(word in key for word in ("PASSWORD", "PASSPHRASE", "SECRET", "TOKEN"))
            or key.endswith("_URL")
            or key == "EMAIL_OUTBOX_KEYS"
        ):
            del env[key]
    password = params.pop("password", None)
    if password is not None:
        env["PGPASSWORD"] = password
    if database is not None:
        params["dbname"] = database
    params.setdefault("connect_timeout", "5")
    directory = os.environ.get("PG_BIN_DIR")
    executable = str(Path(directory) / tool) if directory else tool
    return [executable, "--dbname", make_conninfo(**params), "--no-password"], env


@contextmanager
def gpg_context(passphrase: str):
    if (
        not 32 <= len(passphrase.encode("utf-8")) <= 256
        or "\n" in passphrase
        or "\r" in passphrase
        or passphrase.startswith("replace-")
    ):
        raise BackupError("Use a generated backup passphrase of 32–256 bytes, without newlines.")
    with tempfile.TemporaryDirectory(prefix="easyearn-gpg-") as directory:
        try:
            yield [
                "gpg",
                "--no-options",
                "--homedir",
                directory,
                "--batch",
                "--no-tty",
                "--pinentry-mode",
                "loopback",
                "--no-symkey-cache",
            ]
        finally:
            subprocess.run(
                ["gpgconf", "--homedir", directory, "--kill", "gpg-agent"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


@contextmanager
def passphrase_pipe(passphrase: str):
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, passphrase.encode("utf-8") + b"\n")
        os.close(write_fd)
        write_fd = -1
        yield read_fd
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)


def _finish(processes: list[subprocess.Popen], timeout: int) -> None:
    try:
        if any(process.wait(timeout=timeout) != 0 for process in reversed(processes)):
            raise BackupError(
                "Backup/restore pipeline failed; inspect tools, access, and key configuration."
            )
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()


def create_backup(url: str, output: Path, passphrase: str, *, timeout: int = 600) -> Path:
    output = Path(output).absolute()
    if not output.name.endswith(".dump.gpg"):
        raise BackupError("Encrypted backup output names must end with .dump.gpg.")
    parent = output.parent
    info = parent.stat()
    if not parent.is_dir() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BackupError("Use an existing, owner-only backup directory (mode 0700).")
    if output.exists() or output.is_symlink():
        raise BackupError("Refusing to overwrite an existing backup path.")
    with connect(url) as db:
        name = db.execute("SELECT current_database()").fetchone()[0]
        assert_dedicated_database(db, name)
        validate_application_schema(db)
        flags = db.execute("""
            SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
                   OR has_database_privilege(current_database(), 'CREATE,TEMP')
                   OR has_schema_privilege('public', 'CREATE')
                   OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = pg_roles.oid)
            FROM pg_roles WHERE rolname = current_user
        """).fetchone()[0]
        writes = db.execute("""
            SELECT bool_or(
                has_table_privilege(format('public.%I', tablename), 'DELETE')
                OR has_any_column_privilege(format('public.%I', tablename), 'INSERT,UPDATE'))
            FROM pg_tables WHERE schemaname = 'public'
        """).fetchone()[0]
        if flags or writes:
            raise BackupError(
                "Use the read-only backup database role, not an administrator/runtime role."
            )
    temporary = parent / f".{output.name}.{uuid4().hex}.part"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        dump_args, env = pg_command("pg_dump", url)
        with (
            os.fdopen(fd, "wb") as destination,
            gpg_context(passphrase) as gpg,
            passphrase_pipe(passphrase) as secret,
        ):
            dump = subprocess.Popen(
                [*dump_args, "--format=custom", "--no-owner", "--no-acl"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            try:
                encrypt = subprocess.Popen(
                    [
                        *gpg,
                        "--passphrase-fd",
                        str(secret),
                        "--cipher-algo",
                        "AES256",
                        "--compress-algo",
                        "none",
                        "--force-mdc",
                        "--symmetric",
                        "--output",
                        "-",
                    ],
                    stdin=dump.stdout,
                    stdout=destination,
                    stderr=subprocess.DEVNULL,
                    pass_fds=(secret,),
                )
                dump.stdout.close()
                _finish([dump, encrypt], timeout)
            finally:
                if dump.poll() is None:
                    dump.kill()
                    dump.wait()
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o400)
        os.link(temporary, output)  # Atomic publication; unlike rename, never overwrites.
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return output
    finally:
        temporary.unlink(missing_ok=True)


def _check_archive(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise BackupError(
            "Use a regular, owner-only encrypted backup file; symlinks are not allowed."
        )


def restore_test(
    admin_url: str,
    archive: Path,
    passphrase: str,
    *,
    timeout: int = 600,
    inspect_restored=None,
) -> dict:
    """Restore only into a fresh generated database; never accepts an existing target."""
    archive = Path(archive).absolute()
    _check_archive(archive)
    suffix = uuid4().hex
    database = f"easyearn_restore_test_{suffix}"
    role = f"easyearn_restore_{suffix}"
    password = uuid4().hex + uuid4().hex
    created_role = False
    created_database = False
    archive_fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(archive_fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        os.close(archive_fd)
        raise BackupError("Backup permissions/type changed; refusing to restore.")
    with os.fdopen(archive_fd, "rb") as encrypted, gpg_context(passphrase) as gpg:
        info = os.fstat(encrypted.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise BackupError("Backup permissions changed; refusing to restore.")
        # Authenticate the entire file before executing any archive SQL.
        with passphrase_pipe(passphrase) as secret, tempfile.TemporaryFile() as status:
            result = subprocess.run(
                [
                    *gpg,
                    "--status-fd",
                    str(status.fileno()),
                    "--passphrase-fd",
                    str(secret),
                    "--decrypt",
                ],
                stdin=encrypted,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(secret, status.fileno()),
                timeout=timeout,
            )
            status.seek(0)
            messages = status.read(65536).splitlines()
            if (
                result.returncode
                or b"[GNUPG:] DECRYPTION_OKAY" not in messages
                or b"[GNUPG:] GOODMDC" not in messages
            ):
                raise BackupError(
                    "Encrypted backup integrity/key verification failed; no target was created."
                )
        with connect(admin_url, autocommit=True) as admin:
            try:
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(role))
                )
                created_role = True
                verifier = admin.pgconn.encrypt_password(
                    password.encode(), role.encode(), b"scram-sha-256"
                ).decode()
                admin.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(verifier)
                    )
                )
                admin.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                        sql.Identifier(database), sql.Identifier(role)
                    )
                )
                created_database = True
                admin.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(database)
                    )
                )
                params = conninfo_to_dict(libpq_url(admin_url))
                params.update(dbname=database, user=role, password=password)
                target = make_conninfo(**params)
                encrypted.seek(0)
                restore_args, env = pg_command("pg_restore", target)
                with passphrase_pipe(passphrase) as secret:
                    decrypt = subprocess.Popen(
                        [*gpg, "--passphrase-fd", str(secret), "--decrypt"],
                        stdin=encrypted,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        pass_fds=(secret,),
                    )
                    try:
                        restore = subprocess.Popen(
                            [
                                *restore_args,
                                "--clean",
                                "--if-exists",
                                "--no-owner",
                                "--no-acl",
                                "--exit-on-error",
                            ],
                            stdin=decrypt.stdout,
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        decrypt.stdout.close()
                        _finish([decrypt, restore], timeout)
                    finally:
                        if decrypt.poll() is None:
                            decrypt.kill()
                            decrypt.wait()
                with connect(target) as db:
                    tables = assert_dedicated_database(db, database)
                    if tables != set(ALL_TABLES):
                        raise BackupError("Restore is missing required application tables.")
                    validate_application_schema(db)
                    counts = {
                        table: db.execute(
                            sql.SQL("SELECT count(*) FROM {}").format(
                                sql.Identifier("public", table)
                            )
                        ).fetchone()[0]
                        for table in ALL_TABLES
                    }
                    if inspect_restored:
                        inspect_restored(db)
                    for table in (
                        "user_sessions",
                        "email_verification_tokens",
                        "password_reset_tokens",
                    ):
                        db.execute(
                            sql.SQL("DELETE FROM {}").format(sql.Identifier("public", table))
                        )
                    unusable = bcrypt.hashpw(
                        secrets.token_urlsafe(48).encode(), bcrypt.gensalt(rounds=12)
                    ).decode("ascii")
                    db.execute("UPDATE users SET password_hash = %s", (unusable,))
                    db.execute("""
                        UPDATE email_outbox SET status = 'discarded', encrypted_payload = NULL,
                        lease_id = NULL, leased_until = NULL, completed_at = CURRENT_TIMESTAMP,
                        last_error_code = 'restore_invalidated'
                        WHERE status IN ('pending', 'processing')
                    """)
                return {
                    "restored_rows": counts,
                    "auth_invalidated": True,
                    "password_recovery_required": True,
                    "temporary_target_removed": True,
                }
            finally:
                if created_database:
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                    )
                if created_role:
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
