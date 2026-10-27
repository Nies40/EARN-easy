import hashlib
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address, ip_network
from math import ceil
from typing import Protocol

from redis.asyncio import BlockingConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from app.core.config import Settings

# Increment and set/repair the expiry atomically. Rejected attempts never extend
# the window. Redis's own TTL avoids dependence on application workers' clocks.
_INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if count == 1 or ttl < 0 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimit:
    name: str
    max_requests: int
    window_seconds: int


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Too many requests.")
        self.retry_after = retry_after


class RateLimitUnavailable(Exception):
    pass


class RateLimiter(Protocol):
    async def check(self, policy: RateLimit, client_ip: str) -> None: ...

    async def aclose(self) -> None: ...


def client_network(host: str) -> str | None:
    try:
        address = ip_address(host)
    except ValueError:
        return None
    if isinstance(address, IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        # Prevent trivial bypass by rotating addresses within one IPv6 subnet.
        return str(ip_network(f"{address}/64", strict=False))
    return str(address)


class RedisRateLimiter:
    def __init__(self, settings: Settings, *, client: Redis | None = None):
        self.prefix = f"{settings.auth_rate_limit_key_prefix}:{settings.app_env}"
        if client is None:
            url = settings.redis_url.get_secret_value()
            tls_options = (
                {"ssl_cert_reqs": "required", "ssl_check_hostname": True}
                if url.startswith("rediss://")
                else {}
            )
            pool = BlockingConnectionPool.from_url(
                url,
                max_connections=settings.redis_max_connections,
                timeout=settings.redis_timeout_seconds,
                socket_connect_timeout=settings.redis_timeout_seconds,
                socket_timeout=settings.redis_timeout_seconds,
                retry=Retry(NoBackoff(), 0),
                **tls_options,
            )
            client = Redis(connection_pool=pool)
        self.client = client

    async def check(self, policy: RateLimit, client_ip: str) -> None:
        identity = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
        key = f"{self.prefix}:{policy.name}:{identity}"
        try:
            result = await self.client.eval(_INCREMENT_WINDOW, 1, key, policy.window_seconds * 1000)
        except (RedisError, OSError, TimeoutError) as error:
            raise RateLimitUnavailable from error
        if (
            not isinstance(result, (list, tuple))
            or len(result) != 2
            or type(result[0]) is not int
            or type(result[1]) is not int
            or result[0] < 1
            or result[1] < 0
        ):
            raise RateLimitUnavailable
        count, ttl_ms = result
        if count > policy.max_requests:
            raise RateLimitExceeded(max(1, ceil(ttl_ms / 1000)))

    async def aclose(self) -> None:
        await self.client.aclose(close_connection_pool=True)
