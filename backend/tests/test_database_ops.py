import json

import pytest

from app.core.config import Settings, get_settings
from app.db.permissions import DatabasePermissionError, DatabaseRoles
from app.ops.backup import BackupError, create_backup, gpg_context, pg_command, restore_test
from app.ops.database import main


@pytest.mark.parametrize("prefix", ["", "A", "x;DROP ROLE x", "x" * 37])
def test_role_names_cannot_inject_sql(prefix):
    with pytest.raises(DatabasePermissionError):
        DatabaseRoles(prefix)


def test_subprocess_connection_arguments_do_not_contain_passwords(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "unrelated-secret")
    args, env = pg_command("pg_dump", "postgresql://backup:private-secret@localhost:5432/easyearn")
    assert "private-secret" not in repr(args)
    assert env["PGPASSWORD"] == "private-secret"
    assert "unrelated-secret" not in repr(args)


def test_pg_tools_can_use_an_explicit_trusted_binary_directory(monkeypatch):
    monkeypatch.setenv("PG_BIN_DIR", "/trusted/tools")
    args, _env = pg_command("pg_restore", "postgresql://backup:secret@localhost/easyearn")
    assert args[0] == "/trusted/tools/pg_restore"


def test_backup_rejects_shared_output_directories_before_connecting(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(BackupError, match="owner-only"):
        create_backup("unused", tmp_path / "backup.dump.gpg", "x" * 64)


def test_backup_does_not_overwrite_existing_files(tmp_path):
    tmp_path.chmod(0o700)
    archive = tmp_path / "existing.dump.gpg"
    archive.write_bytes(b"existing user work")
    with pytest.raises(BackupError, match="overwrite"):
        create_backup("unused", archive, "x" * 64)
    assert archive.read_bytes() == b"existing user work"


def test_restore_rejects_symlinks_before_connecting(tmp_path):
    archive = tmp_path / "archive"
    archive.write_bytes(b"data")
    link = tmp_path / "linked"
    link.symlink_to(archive)
    with pytest.raises(BackupError, match="symlinks"):
        restore_test("unused", link, "x" * 64)


@pytest.mark.parametrize(
    "secret",
    ["short", "x" * 257, "x" * 32 + "\n", "replace-with-a-generated-secret-of-at-least-32-bytes"],
)
def test_backup_passphrase_bounds(secret):
    with pytest.raises(BackupError, match="32–256"):
        with gpg_context(secret):
            pass


def test_operator_cli_reports_errors_without_echoing_credentials(monkeypatch, capsys):
    monkeypatch.setenv("BACKUP_DATABASE_URL", "postgresql://user:private-password@private-host/db")
    monkeypatch.setenv("BACKUP_ENCRYPTION_PASSPHRASE", "private-backup-key" * 3)
    assert main(["backup", "--output", "/nonexistent/backup.dump.gpg"]) == 1
    text = capsys.readouterr().err
    assert "private-password" not in text and "private-backup-key" not in text


def test_operator_cli_generates_only_new_distinct_secrets(capsys):
    assert main(["generate-secrets"]) == 0
    values = json.loads(capsys.readouterr().out)
    assert len(values) == len(set(values.values())) == 5
    assert all(len(value) >= 32 for value in values.values())


def test_database_settings_and_invalid_url_errors_redact_passwords():
    value = "postgresql+psycopg://user:private-db-password@localhost/easyearn"
    settings = Settings(_env_file=None, database_url=value)
    assert "private-db-password" not in repr(settings)
    assert settings.database_url.get_secret_value() == value
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None, database_url="invalid://user:private-db-password@localhost/db")
    assert "private-db-password" not in str(caught.value)


def test_each_process_can_load_its_own_private_environment_file(tmp_path, monkeypatch):
    worker = tmp_path / ".env.worker"
    value = "postgresql+psycopg://worker:private-worker-secret@localhost/workerdb"
    worker.write_text("DATABASE_URL=" + value + "\n")
    monkeypatch.setenv("EASYEARN_ENV_FILE", str(worker))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().database_url.get_secret_value() == value
    finally:
        get_settings.cache_clear()
