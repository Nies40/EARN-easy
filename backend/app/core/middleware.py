from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import Settings


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            # Accept the API origin (app_url) and the frontend origin (frontend_url).
            # CORS middleware handles browser preflight and cross-origin headers;
            # here we only reject requests with an unknown Origin header.
            # In development, the browser may use 127.0.0.1 or localhost interchangeably,
            # so accept both variants of each configured origin.
            app_origin = str(self.settings.app_url).rstrip("/")
            frontend_origin = self.settings.frontend_url.rstrip("/")
            allowed_origins = {app_origin, frontend_origin}
            for o in (app_origin, frontend_origin):
                if "localhost" in o:
                    allowed_origins.add(o.replace("localhost", "127.0.0.1"))
                if "127.0.0.1" in o:
                    allowed_origins.add(o.replace("127.0.0.1", "localhost"))
            if origin is not None and origin not in allowed_origins:
                response = JSONResponse(
                    {"error": "Cross-origin requests are not allowed."}, 403
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # FastAPI's development documentation loads its own CDN assets and inline script.
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'"
            )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if self.settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
