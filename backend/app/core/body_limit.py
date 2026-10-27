from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Bound API body buffering, including streamed bodies with no Content-Length."""

    def __init__(self, app: ASGIApp, *, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root) :]
        if scope["type"] != "http" or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        lengths = Headers(scope=scope).getlist("content-length")
        try:
            declared = int(lengths[0]) if lengths else None
            if len(lengths) > 1 or (declared is not None and declared < 0):
                raise ValueError
        except ValueError:
            response = JSONResponse({"error": "Invalid Content-Length header."}, 400)
            await response(scope, receive, send)
            return
        if declared is not None and declared > self.max_bytes:
            await self.reject(scope, receive, send)
            return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                await self.reject(scope, receive, send)
                return
            if body:
                chunks.append(body)
            if not message.get("more_body", False):
                break
        buffered = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"error": "Request body is too large."}, 413, headers={"Cache-Control": "no-store"}
        )
        await response(scope, receive, send)
