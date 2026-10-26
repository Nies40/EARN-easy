import json
from unittest.mock import AsyncMock, Mock

import bcrypt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core import security
from app.core.config import Settings
from app.core.rate_limit import RedisRateLimiter
from app.db.base import Base
from app.integrations.email import OutgoingEmail
from app.main import create_app
from app.modules.outbox.worker import EmailWorker


@pytest.fixture(autouse=True)
def inexpensive_test_hashes(monkeypatch):
    # Test-process-only keys; no application fallback or committed encryption key.
    monkeypatch.setenv("EMAIL_OUTBOX_KEYS", json.dumps([Fernet.generate_key().decode("ascii")]))
    # Production always uses cost 12. Only the isolated test process uses cost 4.
    monkeypatch.setattr(security, "BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(
        security, "DUMMY_PASSWORD_HASH", bcrypt.hashpw(b"dummy-test-password", bcrypt.gensalt(4))
    )


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="test",
        app_url="http://testserver",
        allowed_hosts=["testserver"],
    )


@pytest.fixture
def email_sender(db, settings):
    class CapturingEmailSender:
        def __init__(self):
            self.messages: list[OutgoingEmail] = []

        def send(self, message: OutgoingEmail) -> None:
            self.messages.append(message)

        def deliver_pending(self) -> None:
            for _ in range(100):
                if not self.worker.process_once():
                    return
            pytest.fail("Test worker did not drain its due jobs.")

    sender = CapturingEmailSender()
    sender.worker = EmailWorker(
        sessionmaker(bind=db.get_bind(), expire_on_commit=False), settings, sender
    )
    return sender


@pytest.fixture
def redis_client():
    client = Mock(spec=Redis)
    client.eval = AsyncMock(return_value=[1, 60000])
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def rate_limiter(settings, redis_client):
    return RedisRateLimiter(settings, client=redis_client)


@pytest.fixture
def client(db, settings, email_sender, rate_limiter):
    app = create_app(settings, rate_limiter=rate_limiter)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client


@pytest.fixture
def signup_payload():
    return {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "password": "a-long-test-password",
        "username": "jane_doe",
        "phone": "+254712345678",
    }
