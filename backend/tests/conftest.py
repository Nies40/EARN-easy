import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db, get_email_sender
from app.core import security
from app.core.config import Settings
from app.db.base import Base
from app.integrations.email import OutgoingEmail
from app.main import create_app


@pytest.fixture(autouse=True)
def inexpensive_test_hashes(monkeypatch):
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
def email_sender():
    class CapturingEmailSender:
        def __init__(self):
            self.messages: list[OutgoingEmail] = []

        def send(self, message: OutgoingEmail) -> None:
            self.messages.append(message)

    return CapturingEmailSender()


@pytest.fixture
def client(db, settings, email_sender):
    app = create_app(settings)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    with TestClient(app) as test_client:
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
