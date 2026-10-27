import asyncio
import socket

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.api.dependencies import get_db
from app.api.rate_limit import auth_policies
from app.core.config import Settings
from app.core.rate_limit import (
    RateLimit,
    RateLimitExceeded,
    RateLimitUnavailable,
    RedisRateLimiter,
    client_network,
)
from app.main import create_app

PROTECTED_PATHS = (
    "/api/signup",
    "/api/login",
    "/api/email-verification/request",
    "/api/email-verification/confirm",
    "/api/password/forgot",
    "/api/password/reset",
)


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_all_authentication_mutations_are_limited_before_validation_or_database_access(
    client, redis_client, settings, path
):
    def forbidden_db():
        pytest.fail("A rejected request must not reach the database.")

    client.app.dependency_overrides[get_db] = forbidden_db
    redis_client.eval.return_value = [auth_policies(settings)[path].max_requests + 1, 25001]
    response = client.post(path, json={})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "26"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.json() == {"error": "Too many requests. Please try again later."}


def test_last_allowed_request_is_admitted_and_retry_after_uses_remaining_ttl(client, redis_client):
    redis_client.eval.side_effect = [[5, 60000], [6, 1234]]
    assert client.post("/api/signup", json={}).status_code == 422
    rejected = client.post("/api/signup", json={})
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"] == "2"


def test_malformed_json_also_consumes_an_attempt(client, redis_client):
    response = client.post("/api/login", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    redis_client.eval.assert_awaited_once()


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_redis_outages_fail_closed_without_logging_credentials_or_payloads(
    client, redis_client, email_sender, caplog, path
):
    redis_client.eval.side_effect = RedisConnectionError("redis://private-user:secret@private-host")
    response = client.post(path, json={"password": "private-password", "token": "private-token"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "no-store"
    assert email_sender.messages == []
    assert "rate limiter unavailable" in caplog.text
    for private in ("secret", "private-host", "private-password", "private-token", "127.0.0.1"):
        assert private not in caplog.text
        assert private not in response.text


def test_redis_outages_do_not_prevent_account_reads_health_checks_or_logout(
    client, redis_client, signup_payload
):
    assert client.post("/api/signup", json=signup_payload).status_code == 201
    redis_client.eval.side_effect = RedisConnectionError("unavailable")
    calls = redis_client.eval.await_count
    assert client.get("/").status_code == 200
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/dashboard").status_code == 403
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401
    assert redis_client.eval.await_count == calls
    assert client.post("/api/login", json={}).status_code == 503


def test_forwarded_headers_cannot_change_the_application_limiter_identity(client, redis_client):
    for address in ("192.0.2.1", "198.51.100.1"):
        client.post(
            "/api/login",
            json={},
            headers={
                "X-Forwarded-For": address,
                "X-Real-IP": address,
                "Forwarded": f"for={address}",
            },
        )
    keys = [call.args[2] for call in redis_client.eval.await_args_list]
    assert len(keys) == 2 and keys[0] == keys[1]
    assert "127.0.0.1" not in keys[0]
    assert "192.0.2.1" not in keys[0]


def test_different_routes_have_separate_quotas_without_persisting_identifiers(client, redis_client):
    client.post("/api/login", json={"identifier": "private@example.com", "password": "private"})
    client.post("/api/password/forgot", json={"email": "missing@example.com"})
    keys = [call.args[2] for call in redis_client.eval.await_args_list]
    assert len(keys) == 2 and keys[0] != keys[1]
    assert ":login:" in keys[0] and ":password-forgot:" in keys[1]
    for key in keys:
        assert "@" not in key and "private" not in key


@pytest.mark.parametrize("path", ["/api/login/", "/api/%6Cogin"])
def test_normalized_route_variants_cannot_bypass_the_limit(client, redis_client, path):
    redis_client.eval.return_value = [999, 5000]
    assert client.post(path, json={}).status_code == 429
    redis_client.eval.assert_awaited_once()


def test_host_and_origin_checks_run_before_redis(client, redis_client):
    assert (
        client.post("/api/login", json={}, headers={"Host": "attacker.example"}).status_code == 400
    )
    assert (
        client.post(
            "/api/login", json={}, headers={"Origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    redis_client.eval.assert_not_awaited()


def test_invalid_peer_address_fails_closed(settings, rate_limiter, redis_client):
    app = create_app(settings, rate_limiter=rate_limiter)
    with TestClient(app, client=("not-an-ip", 50000)) as client:
        assert client.post("/api/login", json={}).status_code == 503
    redis_client.eval.assert_not_awaited()


def test_an_asgi_root_path_cannot_bypass_the_limiter(settings, rate_limiter, redis_client):
    redis_client.eval.return_value = [999, 5000]
    app = create_app(settings, rate_limiter=rate_limiter)
    with TestClient(app, root_path="/platform", client=("127.0.0.1", 50000)) as client:
        response = client.post("/platform/api/login", json={})
    assert response.status_code == 429
    assert response.headers["Cache-Control"] == "no-store"
    redis_client.eval.assert_awaited_once()


def test_lifecycle_closes_the_redis_pool(settings, rate_limiter, redis_client):
    with TestClient(create_app(settings, rate_limiter=rate_limiter)):
        pass
    redis_client.aclose.assert_awaited_once_with(close_connection_pool=True)


def test_openapi_describes_limiter_errors_only_for_protected_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in PROTECTED_PATHS:
        responses = paths[path]["post"]["responses"]
        assert "Retry-After" in responses["429"]["headers"]
        assert "503" in responses
    assert "503" not in paths["/api/logout"]["post"]["responses"]


def test_every_authentication_write_except_logout_has_an_explicit_policy(client, settings):
    paths = client.get("/openapi.json").json()["paths"]
    mutations = {
        path
        for path, methods in paths.items()
        if "Authentication" in methods.get("post", {}).get("tags", [])
    }
    assert mutations - {"/api/logout"} == set(auth_policies(settings))


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("::ffff:192.0.2.1", "192.0.2.1"),
        ("2001:0db8:0001:0002::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2::abcd", "2001:db8:1:2::/64"),
        ("fe80::1%eth0", "fe80::/64"),
        ("not-an-ip", None),
        ("", None),
    ],
)
def test_client_network_normalization(host, expected):
    assert client_network(host) == expected


@pytest.mark.parametrize("ttl", [0, 1, 999, 1000, 1001])
def test_positive_retry_after_rounds_up_to_whole_seconds(rate_limiter, redis_client, ttl):
    redis_client.eval.return_value = [11, ttl]
    with pytest.raises(RateLimitExceeded) as caught:
        asyncio.run(rate_limiter.check(RateLimit("login", 10, 60), "127.0.0.1"))
    assert caught.value.retry_after == max(1, (ttl + 999) // 1000)


@pytest.mark.parametrize(
    "result", [None, [], [1], [0, 100], [1, -1], [True, 100], [1, "100"], [1, 100, 1]]
)
def test_unexpected_redis_responses_fail_closed(rate_limiter, redis_client, result):
    redis_client.eval.return_value = result
    with pytest.raises(RateLimitUnavailable):
        asyncio.run(rate_limiter.check(RateLimit("login", 10, 60), "127.0.0.1"))


@pytest.mark.parametrize("error", [RedisTimeoutError(), ResponseError(), OSError(), TimeoutError()])
def test_redis_protocol_and_network_errors_fail_closed(rate_limiter, redis_client, error):
    redis_client.eval.side_effect = error
    with pytest.raises(RateLimitUnavailable):
        asyncio.run(rate_limiter.check(RateLimit("login", 10, 60), "127.0.0.1"))


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:6379/0",
        "redis://localhost:6379/-1",
        "redis://localhost:6379/not-a-db",
        "rediss://localhost:6379/0?ssl_cert_reqs=none",
        "redis://localhost:6379/0?socket_timeout=999",
        "redis://localhost:6379/0#fragment",
    ],
)
def test_invalid_or_unsafe_redis_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_url=url)


def test_redis_credentials_are_redacted():
    settings = Settings(
        _env_file=None, redis_url="rediss://user:redis-private-secret@localhost:6380/1"
    )
    assert "redis-private-secret" not in repr(settings)
    assert "redis-private-secret" not in str(settings.redis_url)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth_rate_limit_signup", 0),
        ("auth_rate_limit_login", -1),
        ("auth_rate_limit_window_seconds", 0),
        ("redis_timeout_seconds", 0),
        ("redis_max_connections", 0),
    ],
)
def test_limits_and_connection_bounds_cannot_be_disabled_by_zero_values(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_real_client_uses_bounded_connection_pool(settings):
    limiter = RedisRateLimiter(settings)
    pool = limiter.client.connection_pool
    assert pool.max_connections == 20
    assert pool.timeout == 0.5
    assert pool.connection_kwargs["socket_timeout"] == 0.5
    assert pool.connection_kwargs["socket_connect_timeout"] == 0.5
    asyncio.run(limiter.aclose())


def test_rediss_requires_certificate_and_hostname_validation():
    settings = Settings(_env_file=None, redis_url="rediss://localhost:6380/0")
    limiter = RedisRateLimiter(settings)
    options = limiter.client.connection_pool.connection_kwargs
    assert options["ssl_cert_reqs"] == "required"
    assert options["ssl_check_hostname"] is True
    asyncio.run(limiter.aclose())


def test_real_connection_refusal_returns_503_without_a_local_fallback():
    # Reserve a local port without listening, so no external service is contacted.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        settings = Settings(
            _env_file=None,
            app_env="test",
            app_url="http://testserver",
            allowed_hosts=["testserver"],
            redis_url=f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0",
            redis_timeout_seconds=0.1,
        )
        with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
            assert client.post("/api/login", json={}).status_code == 503
            assert client.get("/").status_code == 200
