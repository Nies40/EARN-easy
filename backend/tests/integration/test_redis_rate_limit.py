import asyncio
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import RateLimit, RateLimitExceeded, RedisRateLimiter
from app.main import create_app

pytestmark = pytest.mark.redis


def test_independent_workers_share_the_same_counter(redis_settings):
    async def run():
        first = RedisRateLimiter(redis_settings)
        second = RedisRateLimiter(redis_settings)
        policy = RateLimit("login", 2, 2)
        try:
            await first.check(policy, "192.0.2.1")
            await second.check(policy, "192.0.2.1")
            with pytest.raises(RateLimitExceeded) as caught:
                await first.check(policy, "192.0.2.1")
            assert 1 <= caught.value.retry_after <= 2
            # Another client network and another endpoint each have their own quota.
            await second.check(policy, "198.51.100.1")
            await second.check(RateLimit("signup", 2, 2), "192.0.2.1")
        finally:
            await first.aclose()
            await second.aclose()

    asyncio.run(run())


def test_application_instances_share_quota_before_processing_request_bodies(redis_settings):
    settings = Settings(
        _env_file=None,
        app_env="test",
        app_url="http://testserver",
        allowed_hosts=["testserver"],
        redis_url=redis_settings.redis_url,
        auth_rate_limit_key_prefix=redis_settings.auth_rate_limit_key_prefix,
        auth_rate_limit_signup=2,
        auth_rate_limit_window_seconds=10,
    )
    first_app = create_app(settings)
    second_app = create_app(settings)
    with (
        TestClient(first_app, client=("192.0.2.1", 50000)) as first,
        TestClient(second_app, client=("192.0.2.1", 50000)) as second,
    ):
        assert first.post("/api/signup", json={}).status_code == 422
        assert (
            second.post(
                "/api/signup", json={}, headers={"X-Forwarded-For": "198.51.100.1"}
            ).status_code
            == 422
        )
        rejected = first.post("/api/signup", json={})
        assert rejected.status_code == 429
        assert 1 <= int(rejected.headers["Retry-After"]) <= 10


def test_atomic_counter_does_not_over_admit_concurrent_requests(redis_settings):
    async def run():
        workers = [RedisRateLimiter(redis_settings) for _ in range(4)]
        policy = RateLimit("concurrent", 7, 10)

        async def attempt(index):
            try:
                await workers[index % len(workers)].check(policy, "192.0.2.1")
            except RateLimitExceeded:
                return False
            return True

        try:
            admitted = await asyncio.gather(*(attempt(index) for index in range(64)))
            assert sum(admitted) == 7
        finally:
            await asyncio.gather(*(worker.aclose() for worker in workers))

    asyncio.run(run())


def test_window_expires_without_rejected_requests_extending_it(redis_settings):
    async def run():
        limiter = RedisRateLimiter(redis_settings)
        policy = RateLimit("expiry", 1, 1)
        identity = hashlib.sha256(b"192.0.2.1").hexdigest()
        key = f"{limiter.prefix}:expiry:{identity}"
        try:
            await limiter.check(policy, "192.0.2.1")
            # Shorten this test's own TTL; a denied attempt must not reset it to one second.
            await limiter.client.pexpire(key, 150)
            with pytest.raises(RateLimitExceeded):
                await limiter.check(policy, "192.0.2.1")
            assert 0 <= await limiter.client.pttl(key) <= 150
            await asyncio.sleep(0.2)
            await limiter.check(policy, "192.0.2.1")
        finally:
            await limiter.aclose()

    asyncio.run(run())


def test_atomic_script_repairs_a_counter_with_no_expiry(redis_settings):
    async def run():
        limiter = RedisRateLimiter(redis_settings)
        policy = RateLimit("repair", 5, 1)
        identity = hashlib.sha256(b"192.0.2.1").hexdigest()
        key = f"{limiter.prefix}:repair:{identity}"
        try:
            await limiter.client.set(key, 2)
            assert await limiter.client.pttl(key) == -1
            await limiter.check(policy, "192.0.2.1")
            assert 0 <= await limiter.client.pttl(key) <= 1000
        finally:
            # Only remove this test's own key, including when an assertion fails.
            await limiter.client.delete(key)
            await limiter.aclose()

    asyncio.run(run())
