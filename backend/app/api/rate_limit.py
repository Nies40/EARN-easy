import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.rate_limit import (
    RateLimit,
    RateLimiter,
    RateLimitExceeded,
    RateLimitUnavailable,
    client_network,
)

logger = logging.getLogger(__name__)

RATE_LIMIT_RESPONSES = {
    429: {
        "description": "An authentication attempt limit or email cooldown was exceeded.",
        "headers": {"Retry-After": {"schema": {"type": "integer"}}},
    },
    503: {
        "description": "Authentication rate limiting is temporarily unavailable.",
        "headers": {"Retry-After": {"schema": {"type": "integer"}}},
    },
}


def auth_policies(settings: Settings) -> dict[str, RateLimit]:
    window = settings.auth_rate_limit_window_seconds
    return {
        "/api/signup": RateLimit("signup", settings.auth_rate_limit_signup, window),
        "/api/login": RateLimit("login", settings.auth_rate_limit_login, window),
        "/api/email-verification/request": RateLimit(
            "verification-request", settings.auth_rate_limit_verification_request, window
        ),
        "/api/email-verification/confirm": RateLimit(
            "verification-confirm", settings.auth_rate_limit_verification_confirm, window
        ),
        "/api/password/forgot": RateLimit(
            "password-forgot", settings.auth_rate_limit_password_forgot, window
        ),
        "/api/password/reset": RateLimit(
            "password-reset", settings.auth_rate_limit_password_reset, window
        ),
    }


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings, limiter: RateLimiter):
        super().__init__(app)
        self.policies = auth_policies(settings)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.scope["path"]
        root_path = request.scope.get("root_path", "")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path) :]
        policy = self.policies.get(path)
        if request.method != "POST" or policy is None:
            return await call_next(request)

        # Only trust the ASGI peer address. Forwarded-header processing, if needed,
        # must be restricted to known proxies in the application server.
        identity = client_network(request.client.host) if request.client else None
        try:
            if identity is None:
                raise RateLimitUnavailable
            await self.limiter.check(policy, identity)
        except RateLimitExceeded as error:
            return JSONResponse(
                {"error": "Too many requests. Please try again later."},
                status_code=429,
                headers={"Retry-After": str(error.retry_after), "Cache-Control": "no-store"},
            )
        except RateLimitUnavailable as error:
            # Never log Redis URLs, credentials, client IPs, or request bodies.
            logger.error(
                "Authentication rate limiter unavailable (%s).",
                type(error.__cause__ or error).__name__,
            )
            return JSONResponse(
                {"error": "Authentication is temporarily unavailable. Please try again."},
                status_code=503,
                headers={"Retry-After": "5", "Cache-Control": "no-store"},
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
