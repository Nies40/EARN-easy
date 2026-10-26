import asyncio

import pytest

from app.api.dependencies import get_db
from app.core.body_limit import RequestBodyLimitMiddleware


def test_oversized_api_requests_do_not_reach_validation_or_database(client, redis_client):
    def forbidden():
        pytest.fail("Oversized requests must not access the database.")

    client.app.dependency_overrides[get_db] = forbidden
    response = client.post("/api/signup", content=b"x" * 20481)
    assert response.status_code == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    redis_client.eval.assert_awaited_once()  # Quota protection still precedes buffering.


@pytest.mark.parametrize("length", ["20481", "-1", "invalid"])
def test_declared_length_is_checked_without_echoing_it(client, length):
    response = client.post("/api/login", content=b"{}", headers={"Content-Length": length})
    assert response.status_code == (413 if length == "20481" else 400)
    assert length not in response.text


@pytest.mark.parametrize("chunks", [[b"123", b"456"], [b"123456"]])
def test_chunked_or_underreported_bodies_cannot_bypass_the_cap(chunks):
    async def run():
        output = []
        events = iter(
            [
                {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
                for i, chunk in enumerate(chunks)
            ]
        )

        async def receive():
            return next(events)

        async def send(event):
            output.append(event)

        async def forbidden(_scope, _receive, _send):
            pytest.fail("Too much input was passed to the downstream app.")

        scope = {
            "type": "http",
            "path": "/mounted/api/login",
            "root_path": "/mounted",
            "headers": [(b"content-length", b"1")],
        }
        await RequestBodyLimitMiddleware(forbidden, max_bytes=5)(scope, receive, send)
        assert output[0]["status"] == 413

    asyncio.run(run())


def test_exactly_at_limit_is_replayed_unchanged():
    async def run():
        captured = []

        async def receive():
            return {"type": "http.request", "body": b"12345", "more_body": False}

        async def app(_scope, incoming, _send):
            captured.append(await incoming())

        async def send(_event):
            pass

        await RequestBodyLimitMiddleware(app, max_bytes=5)(
            {"type": "http", "path": "/api/login", "headers": []}, receive, send
        )
        assert captured[0]["body"] == b"12345"

    asyncio.run(run())
