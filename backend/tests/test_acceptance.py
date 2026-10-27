import json

import pytest

from app.ops.acceptance import (
    AcceptanceError,
    child_environment,
    fresh_database,
    main,
    percentile,
    require_local_host,
    validate_services,
    write_environment,
)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.2.3.4", "::1", "/private/socket"])
def test_acceptance_allows_only_local_test_hosts(host):
    require_local_host(host)


@pytest.mark.parametrize(
    "host", ["production.example.com", "192.0.2.1", "localhost,production", ""]
)
def test_acceptance_rejects_remote_or_ambiguous_hosts(host):
    with pytest.raises(AcceptanceError):
        require_local_host(host)


def test_pg_hostaddr_cannot_override_the_local_only_guard():
    with pytest.raises(AcceptanceError):
        validate_services(
            "postgresql://operator@localhost/postgres?hostaddr=192.0.2.1",
            "redis://localhost:6379/0",
        )


def test_runtime_children_do_not_inherit_admin_or_existing_app_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "private-admin-url")
    monkeypatch.setenv("SMTP_PASSWORD", "private-smtp-password")
    monkeypatch.setenv("ACCEPTANCE_DATABASE_ADMIN_URL", "private-acceptance-url")
    path = write_environment(
        tmp_path / "api.env", {"APP_ENV": "test", "DATABASE_URL": "isolated-runtime-url"}
    )
    env = child_environment(path)
    assert env["DATABASE_URL"] == "isolated-runtime-url"
    assert "SMTP_PASSWORD" not in env
    assert "ACCEPTANCE_DATABASE_ADMIN_URL" not in env


def test_child_environment_missing_file_never_falls_back_to_app_defaults(tmp_path):
    with pytest.raises(AcceptanceError, match="missing"):
        child_environment(tmp_path / "missing.env")


def test_private_environments_roundtrip_json_values(tmp_path):
    from dotenv import dotenv_values

    path = write_environment(
        tmp_path / "api.env", {"KEY_RING": '["sample-key"]', "VALUE": "a'b\"c"}
    )
    values = dotenv_values(path)
    assert json.loads(values["KEY_RING"]) == ["sample-key"]
    assert values["VALUE"] == "a'b\"c"
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_environment(path, {})


def test_percentiles_use_nearest_rank():
    assert percentile(list(range(1, 21)), 0.95) == 19
    assert percentile([0.2], 0.99) == 0.2
    assert percentile([], 0.95) == 0


def test_cli_requires_explicit_disposable_cluster_confirmation():
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2


def test_cli_never_uses_application_database_as_implicit_test_target(monkeypatch, capsys):
    monkeypatch.delenv("ACCEPTANCE_DATABASE_ADMIN_URL", raising=False)
    monkeypatch.delenv("ACCEPTANCE_REDIS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "private-application-url")
    assert main(["--confirm-disposable-cluster"]) == 2
    assert "private-application-url" not in capsys.readouterr().out


@pytest.mark.parametrize("target", ["nan", "inf", "0", "-1"])
def test_cli_requires_finite_positive_latency_targets(target):
    with pytest.raises(SystemExit) as caught:
        main(["--confirm-disposable-cluster", "--registration-p95-seconds", target])
    assert caught.value.code == 2


def test_failed_provisioning_never_drops_preexisting_roles(monkeypatch):
    statements = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, statement):
            statements.append(statement.as_string())

    def failed(*_args):
        raise AcceptanceError("Role names already exist.")

    monkeypatch.setattr("app.ops.acceptance.connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr("app.ops.acceptance.provision_roles", failed)
    with pytest.raises(AcceptanceError, match="already exist"):
        with fresh_database("unused", {"host": "localhost", "dbname": "postgres", "user": "admin"}):
            pytest.fail("Provisioning should not succeed.")
    assert any(statement.startswith("DROP DATABASE") for statement in statements)
    assert not any(statement.startswith("DROP ROLE") for statement in statements)
