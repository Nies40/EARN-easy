"""Isolated local acceptance checks; never targets an existing application database."""

import argparse
import ipaddress
import json
import math
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread
from time import monotonic, perf_counter, sleep
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import bcrypt
import httpx
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from psycopg import sql
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app.db.permissions import DatabaseRoles, check_runtime_database_role, provision_roles
from app.ops.backup import connect, connection_parameters

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class AcceptanceError(ValueError):
    pass


def require_local_host(host: str) -> None:
    if host == "localhost" or host.startswith("/"):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise AcceptanceError("Acceptance checks require an isolated local database and Redis server.")


def validate_services(admin_url: str, redis_url: str) -> dict:
    params = connection_parameters(admin_url)
    for field in ("host", "hostaddr"):
        if params.get(field):
            require_local_host(params[field])
    redis = urlsplit(redis_url)
    if redis.scheme not in ("redis", "rediss") or not redis.hostname:
        raise AcceptanceError("An explicit Redis test URL is required.")
    require_local_host(redis.hostname)
    return params


def child_environment(env_file: Path) -> dict:
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR")
    result = {name: os.environ[name] for name in allowed if name in os.environ}
    if not env_file.is_file():
        raise AcceptanceError("A generated test environment is missing; refusing to use defaults.")
    values = dotenv_values(env_file, interpolate=False)
    if values.get("APP_ENV") != "test" or not values.get("DATABASE_URL"):
        raise AcceptanceError("Child environments must explicitly identify their test database.")
    result.update({name: value for name, value in values.items() if value is not None})
    result.update(EASYEARN_ENV_FILE=str(env_file), PYTHONUNBUFFERED="1")
    return result


def write_environment(path: Path, values: dict) -> Path:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        for name, value in values.items():
            output.write(f"{name}={json.dumps(str(value), ensure_ascii=False)}\n")
    return path


def run_child(arguments: list[str], environment: Path, log: Path) -> None:
    with log.open("ab") as output:
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=BACKEND_ROOT,
            env=child_environment(environment),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            timeout=60,
        )
    if result.returncode:
        raise AcceptanceError("A migration/worker child process failed; acceptance did not pass.")


@contextmanager
def fresh_database(admin_url: str, params: dict):
    database = "easyearn_acceptance_" + uuid4().hex
    roles = DatabaseRoles("acc_" + uuid4().hex[:16])
    passwords = {
        kind: secrets.token_urlsafe(32) for kind in ("migrator", "api", "worker", "backup")
    }
    source = dict(params, dbname=database)
    created_roles = False
    with connect(admin_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database))
        )
        try:
            with connect(make_conninfo(**source)) as db:
                provision_roles(db, database, roles, passwords)
            created_roles = True
            urls = {}
            for kind, password in passwords.items():
                query = {
                    key: value
                    for key, value in params.items()
                    if key not in ("user", "password", "dbname", "host", "port")
                }
                local_socket = params["host"].startswith("/")
                if local_socket:
                    query.update(host=params["host"], port=params.get("port", "5432"))
                urls[kind] = URL.create(
                    "postgresql+psycopg",
                    username=roles.name(kind),
                    password=password,
                    host="localhost" if local_socket else params["host"],
                    port=None if local_socket else int(params.get("port", 5432)),
                    database=database,
                    query=query,
                ).render_as_string(hide_password=False)
            yield roles, urls
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            if created_roles:
                for kind in ("api", "worker", "backup", "migrator", "owner"):
                    admin.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(roles.name(kind)))
                    )


@contextmanager
def smtp_sink():
    messages = []

    class Handler(StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(10)
            self.wfile.write(b"220 localhost acceptance SMTP\r\n")
            while line := self.rfile.readline():
                command = line.split(b" ", 1)[0].strip().upper()
                if command == b"DATA":
                    self.wfile.write(b"354 End with a dot\r\n")
                    data = bytearray()
                    while chunk := self.rfile.readline():
                        if chunk == b".\r\n":
                            break
                        data.extend(chunk[1:] if chunk.startswith(b"..") else chunk)
                    messages.append(BytesParser(policy=policy.default).parsebytes(bytes(data)))
                    self.wfile.write(b"250 Accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 localhost\r\n")

    with TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield server.server_address[1], messages
        finally:
            server.shutdown()
            thread.join(timeout=5)


@contextmanager
def api_server(listener: socket.socket, environment: Path, log: Path, base_url: str):
    with log.open("ab") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--fd",
                str(listener.fileno()),
                "--no-proxy-headers",
                "--no-access-log",
                "--log-level",
                "warning",
            ],
            cwd=BACKEND_ROOT,
            env=child_environment(environment),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            pass_fds=(listener.fileno(),),
        )
        try:
            deadline = monotonic() + 30
            with httpx.Client(base_url=base_url, timeout=1, trust_env=False) as client:
                while monotonic() < deadline:
                    if process.poll() is not None:
                        raise AcceptanceError("API exited before becoming ready.")
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    sleep(0.1)
                else:
                    raise AcceptanceError("API readiness deadline was exceeded.")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def expect(response: httpx.Response, code: int, step: str) -> None:
    if response.status_code != code:
        raise AcceptanceError(f"{step}: expected HTTP {code}, received {response.status_code}.")


def last_token(messages: list, expected_subject: str) -> str:
    if not messages or str(messages[-1]["Subject"]) != expected_subject:
        raise AcceptanceError("The expected account email was not delivered.")
    text = messages[-1].get_body(preferencelist=("plain",)).get_content()
    link = next(line for line in text.splitlines() if line.startswith("http"))
    return parse_qs(urlsplit(link).fragment)["token"][0]


def end_to_end(base_url: str, urls: dict, worker_env: Path, log: Path, messages: list) -> dict:
    email = f"acceptance-{uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        expect(client.get("/"), 200, "frontend entry point")
        expect(client.get("/assets/js/auth.js"), 200, "frontend script")
        payload = {"name": "Acceptance User", "email": email, "password": password}
        response = client.post("/api/signup", json=payload)
        expect(response, 201, "registration")
        with connect(urls["api"]) as db:
            stored = db.execute(
                "SELECT password_hash FROM users WHERE email = %s", (email,)
            ).fetchone()[0]
            if not stored.startswith("$2b$12$"):
                raise AcceptanceError("The real API process must use bcrypt cost 12.")
        if "HttpOnly" not in response.headers.get("set-cookie", ""):
            raise AcceptanceError("Session cookie is missing HttpOnly.")
        expect(client.get("/api/me"), 200, "limited account")
        expect(client.get("/api/dashboard"), 403, "unverified dashboard denial")
        expect(client.post("/api/signup", json=payload), 409, "duplicate registration")
        if messages:
            raise AcceptanceError("Email must be queued, not delivered inside the API request.")
        run_child(["-m", "app.workers.email", "--once"], worker_env, log)
        token = last_token(messages, "Verify your Easyearn email")
        expect(
            client.post("/api/email-verification/confirm", json={"token": token}),
            200,
            "verification",
        )
        expect(client.get("/api/dashboard"), 200, "verified dashboard")
        expect(
            client.post("/api/email-verification/confirm", json={"token": token}), 400, "single use"
        )
        old_cookie = client.cookies.get("easyearn_session")
        known = client.post("/api/password/forgot", json={"email": email})
        unknown = client.post("/api/password/forgot", json={"email": "missing@example.com"})
        expect(known, 202, "recovery request")
        expect(unknown, 202, "unknown recovery request")
        if known.json() != unknown.json():
            raise AcceptanceError("Recovery response disclosed account existence.")
        run_child(["-m", "app.workers.email", "--once"], worker_env, log)
        reset_token = last_token(messages, "Reset your Easyearn password")
        replacement = secrets.token_urlsafe(24)
        expect(
            client.post(
                "/api/password/reset", json={"token": reset_token, "password": replacement}
            ),
            200,
            "reset",
        )
        expect(
            client.get("/api/me", headers={"Cookie": f"easyearn_session={old_cookie}"}),
            401,
            "revocation",
        )
        expect(
            client.post("/api/login", json={"identifier": email, "password": password}),
            401,
            "old password denial",
        )
        expect(
            client.post("/api/login", json={"identifier": email.upper(), "password": replacement}),
            200,
            "new login",
        )
        expect(client.get("/api/dashboard"), 200, "verified status preserved")
        expect(client.post("/api/logout"), 200, "logout")
        expect(client.get("/api/me"), 401, "anonymous denial")
        expect(client.post("/api/login", content=b"x" * 20481), 413, "body-size protection")
    with connect(urls["worker"]) as db:
        state = db.execute("SELECT status, encrypted_payload FROM email_outbox").fetchall()
        if len(state) != 2 or any(status != "sent" or body is not None for status, body in state):
            raise AcceptanceError("Delivery jobs were not completed and scrubbed.")
    return {
        "passed": True,
        "transport": "local HTTP/TCP",
        "smtp_messages": len(messages),
        "separate_api_worker_processes": True,
        "restricted_roles": True,
        "bcrypt_cost": 12,
        "production_tls": "separate staging sign-off required",
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def seed_accounts(url: str, count: int, password: str) -> list[str]:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode("ascii")
    emails = [f"seed-{uuid4().hex}@example.com" for _ in range(count)]
    with (
        connect(url) as db,
        db.cursor().copy(
            "COPY users (id, name, email, password_hash, email_verified_at) FROM STDIN"
        ) as copy,
    ):
        for email in emails:
            copy.write_row((uuid4(), "Synthetic Account", email, password_hash, datetime.now(UTC)))
    return emails


def measure_requests(
    base_url: str, path: str, payloads: list[dict], concurrency: int, start_ip: int
) -> dict:
    def request(item):
        index, payload = item
        source = str(
            ipaddress.IPv4Address(int(ipaddress.IPv4Address("127.2.0.1")) + start_ip + index)
        )
        transport = httpx.HTTPTransport(local_address=source, retries=0)
        with httpx.Client(
            base_url=base_url, transport=transport, timeout=15, trust_env=False
        ) as client:
            started = perf_counter()
            try:
                response = client.post(path, json=payload)
                return perf_counter() - started, str(response.status_code)
            except httpx.HTTPError as error:
                return perf_counter() - started, type(error).__name__

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(request, enumerate(payloads)))
    elapsed = perf_counter() - started
    values = [duration for duration, _status in results]
    return {
        "requests": len(results),
        "concurrency": concurrency,
        "statuses": dict(Counter(status for _duration, status in results)),
        "p50_seconds": round(percentile(values, 0.5), 4),
        "p95_seconds": round(percentile(values, 0.95), 4),
        "p99_seconds": round(percentile(values, 0.99), 4),
        "max_seconds": round(max(values), 4),
        "elapsed_seconds": round(elapsed, 4),
        "requests_per_second": round(len(results) / elapsed, 3),
    }


def benchmark(
    base_url: str,
    api_url: str,
    *,
    accounts: int,
    requests: int,
    concurrency: int,
    registration_target: float,
    login_target: float,
) -> dict:
    password = secrets.token_urlsafe(24)
    emails = seed_accounts(api_url, accounts, password)
    registrations = [
        {
            "name": "Synthetic Registration",
            "email": f"load-{uuid4().hex}@example.com",
            "password": password,
        }
        for _ in range(requests)
    ]
    logins = [
        {"identifier": emails[index % len(emails)], "password": password}
        for index in range(requests)
    ]
    signup = measure_requests(base_url, "/api/signup", registrations, concurrency, 1000)
    login = measure_requests(base_url, "/api/login", logins, concurrency, 5000)
    passed = (
        signup["statuses"] == {"201": requests}
        and login["statuses"] == {"200": requests}
        and signup["p95_seconds"] < registration_target
        and login["p95_seconds"] < login_target
    )
    return {
        "passed": passed,
        "seeded_existing_accounts": accounts,
        "bcrypt_cost": 12,
        "registration_p95_target_seconds": registration_target,
        "login_p95_target_seconds": login_target,
        "registration": signup,
        "login": login,
        "limits_enabled": True,
        "source_addresses": "distinct real IPv4 loopback peers",
        "delivery_worker_during_timing": "idle; API queueing latency only",
        "model": (
            "closed-loop local batch; timings include HTTP request/response, "
            "not client construction"
        ),
    }


def run_acceptance(admin_url: str, redis_url: str, *, load: dict | None = None) -> dict:
    params = validate_services(admin_url, redis_url)
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "logical_cpus": os.cpu_count(),
        "status": "failed",
        "scope": "fresh local database and generated roles only; no production acceptance",
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=BACKEND_ROOT, capture_output=True, text=True
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=BACKEND_ROOT, capture_output=True, text=True
    )
    report["source"] = {
        "commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "working_tree_dirty": bool(dirty.stdout.strip()),
    }
    with tempfile.TemporaryDirectory(prefix="easyearn-acceptance-") as directory:
        directory = Path(directory)
        log = directory / "children.log"
        with fresh_database(admin_url, params) as (roles, urls):
            migration = write_environment(
                directory / "migration.env",
                {
                    "APP_ENV": "test",
                    "DATABASE_URL": urls["migrator"],
                    "DATABASE_ROLE_PREFIX": roles.prefix,
                },
            )
            run_child(
                ["-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), "upgrade", "head"],
                migration,
                log,
            )
            run_child(
                ["-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), "check"], migration, log
            )
            for kind in ("api", "worker"):
                engine = create_engine(urls[kind], hide_parameters=True)
                try:
                    check_runtime_database_role(engine, kind)
                finally:
                    engine.dispose()
            with smtp_sink() as (smtp_port, messages), socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
                common = {
                    "APP_ENV": "test",
                    "APP_URL": base_url,
                    "ALLOWED_HOSTS": '["127.0.0.1"]',
                    "EMAIL_OUTBOX_KEYS": json.dumps([Fernet.generate_key().decode("ascii")]),
                    "SMTP_HOST": "127.0.0.1",
                    "SMTP_PORT": smtp_port,
                    "SMTP_TLS_MODE": "none",
                    "SMTP_FROM_EMAIL": "no-reply@example.com",
                    "REDIS_URL": redis_url,
                    "AUTH_RATE_LIMIT_KEY_PREFIX": "acceptance-" + uuid4().hex,
                }
                api = write_environment(
                    directory / "api.env", dict(common, DATABASE_URL=urls["api"])
                )
                worker = write_environment(
                    directory / "worker.env", dict(common, DATABASE_URL=urls["worker"])
                )
                with api_server(listener, api, log, base_url):
                    report["fresh_install"] = {
                        "passed": True,
                        "migrations": "upgrade and drift check",
                    }
                    report["end_to_end"] = end_to_end(base_url, urls, worker, log, messages)
                    if load is not None:
                        report["benchmark"] = benchmark(base_url, urls["api"], **load)
            report["status"] = (
                "passed" if report.get("benchmark", {}).get("passed", True) else "failed"
            )
    report["temporary_database_roles_and_processes_removed"] = True
    return report


def bounded_int(value: str) -> int:
    result = int(value)
    if not 1 <= result <= 100000:
        raise argparse.ArgumentTypeError("Use an integer between 1 and 100000.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local, disposable backend acceptance and optional load baseline."
    )
    parser.add_argument("--confirm-disposable-cluster", action="store_true", required=True)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--seed-users", type=bounded_int, default=10000)
    parser.add_argument("--requests", type=bounded_int, default=20)
    parser.add_argument("--concurrency", type=bounded_int, default=5)
    parser.add_argument("--registration-p95-seconds", type=float, default=2)
    parser.add_argument("--login-p95-seconds", type=float, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.concurrency > 64 or args.requests > 1000 or args.seed_users < args.requests:
        parser.error(
            "Use at most 64 clients/1000 requests and at least one existing account per login."
        )
    if any(
        not math.isfinite(value) or value <= 0
        for value in (args.registration_p95_seconds, args.login_p95_seconds)
    ):
        parser.error("Latency targets must be positive seconds.")
    try:
        if args.output and (args.output.exists() or not args.output.parent.is_dir()):
            raise AcceptanceError("Choose a new report file in an existing directory.")
        admin = os.environ.get("ACCEPTANCE_DATABASE_ADMIN_URL")
        redis = os.environ.get("ACCEPTANCE_REDIS_URL")
        if not admin or not redis:
            raise AcceptanceError(
                "Set both explicit ACCEPTANCE_DATABASE_ADMIN_URL and ACCEPTANCE_REDIS_URL."
            )
        load = (
            {
                "accounts": args.seed_users,
                "requests": args.requests,
                "concurrency": args.concurrency,
                "registration_target": args.registration_p95_seconds,
                "login_target": args.login_p95_seconds,
            }
            if args.benchmark
            else None
        )
        report = run_acceptance(admin, redis, load=load)
        text = json.dumps(report, indent=2)
        if args.output:
            with os.fdopen(
                os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
            ) as output:
                output.write(text + "\n")
        print(text)
        return 0 if report["status"] == "passed" else 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": (
                        "Acceptance did not complete; no credentials or child logs are displayed."
                    ),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
