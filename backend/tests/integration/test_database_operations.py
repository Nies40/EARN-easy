import os
import secrets
import shutil
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import bcrypt
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.db.permissions import (
    DatabasePermissionError,
    DatabaseRoles,
    apply_runtime_grants,
    check_runtime_database_role,
    provision_roles,
)
from app.main import create_app
from app.modules.auth import service
from app.modules.auth.schemas import SignupRequest
from app.modules.outbox.crypto import EmailPayloadCipher
from app.modules.outbox.models import EmailJob
from app.modules.outbox.worker import EmailWorker
from app.ops.backup import BackupError, connect, connection_parameters, create_backup, restore_test

pytestmark = pytest.mark.dbops


@dataclass
class RoleDatabase:
    name: str
    roles: DatabaseRoles
    urls: dict = field(repr=False)
    passwords: dict = field(repr=False)
    admin_url: str = field(repr=False)


@pytest.fixture
def role_database(monkeypatch):
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_ADMIN_URL to test isolated database operations.")
    name = "easyearn_role_test_" + uuid4().hex
    roles = DatabaseRoles("ee_" + uuid4().hex[:16])
    passwords = {
        kind: secrets.token_urlsafe(32) for kind in ("migrator", "api", "worker", "backup")
    }
    params = connection_parameters(admin_url)
    params["dbname"] = name
    source_admin = make_conninfo(**params)
    urls = {}
    for kind, password in passwords.items():
        local_socket = params["host"].startswith("/")
        urls[kind] = URL.create(
            "postgresql+psycopg",
            username=roles.name(kind),
            password=password,
            host="localhost" if local_socket else params["host"],
            port=None if local_socket else int(params.get("port", 5432)),
            database=name,
            query={"host": params["host"], "port": params.get("port", "5432")}
            if local_socket
            else {},
        ).render_as_string(hide_password=False)
    with connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        created_roles = False
        try:
            with connect(source_admin) as db:
                provision_roles(db, name, roles, passwords)
            created_roles = True
            monkeypatch.setenv("DATABASE_URL", urls["migrator"])
            monkeypatch.setenv("DATABASE_ROLE_PREFIX", roles.prefix)
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            get_settings.cache_clear()
            yield RoleDatabase(name, roles, urls, passwords, source_admin)
        finally:
            get_settings.cache_clear()
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            if created_roles:
                for kind in ("api", "worker", "backup", "migrator", "owner"):
                    admin.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(roles.name(kind)))
                    )


def test_runtime_roles_execute_real_auth_delivery_and_deny_excess_privileges(
    role_database, settings, signup_payload, email_sender, rate_limiter
):
    api_engine = create_engine(role_database.urls["api"], hide_parameters=True)
    worker_engine = create_engine(role_database.urls["worker"], hide_parameters=True)
    try:
        check_runtime_database_role(api_engine, "api")
        check_runtime_database_role(worker_engine, "worker")
        production = Settings(
            _env_file=None,
            app_env="production",
            app_url="https://testserver",
            allowed_hosts=["testserver"],
            database_url=role_database.urls["api"],
            smtp_tls_mode="ssl",
            smtp_from_email="no-reply@example.org",
        )
        app = create_app(production, rate_limiter=rate_limiter)
        worker = EmailWorker(sessionmaker(worker_engine), settings, email_sender)

        def delivered_token():
            link = next(
                line
                for line in email_sender.messages[-1].body.splitlines()
                if line.startswith("http")
            )
            return parse_qs(urlsplit(link).fragment)["token"][0]

        with TestClient(app, base_url="https://testserver", client=("127.0.0.1", 50000)) as client:
            response = client.post("/api/signup", json=signup_payload)
            assert response.status_code == 201
            user_id = response.json()["user"]["id"]
            assert worker.process_once()
            response = client.post(
                "/api/email-verification/confirm", json={"token": delivered_token()}
            )
            assert response.status_code == 200
            assert client.get("/api/dashboard").status_code == 200
            response = client.post("/api/password/forgot", json={"email": signup_payload["email"]})
            assert response.status_code == 202
            assert worker.process_once()
            response = client.post(
                "/api/password/reset",
                json={"token": delivered_token(), "password": "restricted-new-password"},
            )
            assert response.status_code == 200
            assert client.get("/api/me").status_code == 401
            response = client.post(
                "/api/login",
                json={"identifier": signup_payload["email"], "password": "restricted-new-password"},
            )
            assert response.status_code == 200
        denied = {
            "api": [
                "CREATE TABLE public.must_not_exist (id int)",
                "DELETE FROM public.users",
                "SELECT encrypted_payload FROM public.email_outbox",
                "UPDATE public.email_outbox SET status = 'failed'",
            ],
            "worker": [
                "SELECT password_hash FROM public.users",
                "UPDATE public.users SET name = 'forbidden'",
                "UPDATE public.user_sessions SET user_id = user_id",
            ],
            "backup": [
                "DELETE FROM public.user_sessions",
                "CREATE TABLE public.must_not_exist (id int)",
            ],
        }
        for kind, statements in denied.items():
            with connect(role_database.urls[kind], autocommit=True) as db:
                for statement in statements:
                    with pytest.raises(psycopg.Error):
                        db.execute(statement)
        with sessionmaker(api_engine)() as db:
            assert service.current_user(db, "unknown") is None
        assert user_id is not None
    finally:
        api_engine.dispose()
        worker_engine.dispose()


def test_encrypted_backup_restore_and_auth_invalidation(
    role_database, settings, signup_payload, tmp_path
):
    if not all(shutil.which(name) for name in ("gpg", "gpgconf")):
        pytest.fail("Database recovery tests require gpg and gpgconf.")
    api_engine = create_engine(role_database.urls["api"], hide_parameters=True)
    try:
        with sessionmaker(api_engine, expire_on_commit=False)() as db:
            service.register(db, SignupRequest(**signup_payload), settings, None)
        tmp_path.chmod(0o700)
        archive = tmp_path / "snapshot.dump.gpg"
        passphrase = secrets.token_urlsafe(48)
        create_backup(role_database.urls["backup"], archive, passphrase)
        assert archive.stat().st_mode & 0o777 == 0o400
        assert signup_payload["email"].encode() not in archive.read_bytes()
        assert not archive.read_bytes().startswith(b"PGDMP")

        def inspect_restored(db):
            row = db.execute(
                "SELECT id, user_id, purpose, token_hash, key_id, encrypted_payload "
                "FROM email_outbox"
            ).fetchone()
            job = EmailJob(
                **dict(
                    zip(
                        ("id", "user_id", "purpose", "token_hash", "key_id", "encrypted_payload"),
                        row,
                        strict=True,
                    )
                )
            )
            assert EmailPayloadCipher(settings).decrypt(job).recipient == signup_payload["email"]
            password_hash = db.execute("SELECT password_hash FROM users").fetchone()[0]
            assert bcrypt.checkpw(signup_payload["password"].encode(), password_hash.encode())

        report = restore_test(
            role_database.admin_url, archive, passphrase, inspect_restored=inspect_restored
        )
        assert report["restored_rows"]["users"] == 1
        assert report["restored_rows"]["email_outbox"] == 1
        assert report["auth_invalidated"] and report["password_recovery_required"]
        assert report["temporary_target_removed"]
        with connect(role_database.urls["backup"]) as source:
            assert source.execute("SELECT count(*) FROM users").fetchone()[0] == 1
            assert source.execute("SELECT count(*) FROM user_sessions").fetchone()[0] == 1
            original_hash = source.execute("SELECT password_hash FROM users").fetchone()[0]
            assert bcrypt.checkpw(signup_payload["password"].encode(), original_hash.encode())
        with pytest.raises(BackupError, match="integrity/key"):
            restore_test(role_database.admin_url, archive, secrets.token_urlsafe(48))
        with pytest.raises(BackupError, match="read-only"):
            create_backup(role_database.admin_url, tmp_path / "admin.dump.gpg", passphrase)
    finally:
        api_engine.dispose()


def test_existing_roles_are_not_reprovisioned_and_memberships_fail_runtime_checks(role_database):
    with connect(role_database.admin_url) as admin:
        verifier = admin.execute(
            "SELECT rolpassword FROM pg_authid WHERE rolname = %s",
            (role_database.roles.name("api"),),
        ).fetchone()[0]
    with pytest.raises(DatabasePermissionError, match="already exist"):
        with connect(role_database.admin_url) as admin:
            provision_roles(
                admin,
                role_database.name,
                role_database.roles,
                role_database.passwords,
                adopt_existing=True,
            )
    with connect(role_database.admin_url) as admin:
        assert (
            admin.execute(
                "SELECT rolpassword FROM pg_authid WHERE rolname = %s",
                (role_database.roles.name("api"),),
            ).fetchone()[0]
            == verifier
        )
        admin.execute(
            sql.SQL("GRANT SELECT (encrypted_payload) ON email_outbox TO {}").format(
                sql.Identifier(role_database.roles.name("api"))
            )
        )
    engine = create_engine(role_database.urls["api"], hide_parameters=True)
    try:
        with pytest.raises(DatabasePermissionError, match="column"):
            check_runtime_database_role(engine, "api")
        with connect(role_database.admin_url) as admin:
            apply_runtime_grants(admin, role_database.roles)
        check_runtime_database_role(engine, "api")
    finally:
        engine.dispose()
    with connect(role_database.admin_url) as admin:
        admin.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(role_database.roles.name("backup")),
                sql.Identifier(role_database.roles.name("api")),
            )
        )
    engine = create_engine(role_database.urls["api"], hide_parameters=True)
    try:
        with pytest.raises(DatabasePermissionError, match="memberships"):
            check_runtime_database_role(engine, "api")
    finally:
        engine.dispose()
