import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings
from app.db.base import Base


@pytest.fixture
def pg_factory():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    if make_url(url).drivername != "postgresql+psycopg":
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg.")
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    schema = f"easyearn_test_{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    translated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(translated)
        yield sessionmaker(bind=translated, expire_on_commit=False)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def redis_settings():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to run Redis integration tests.")
    return Settings(
        _env_file=None,
        app_env="test",
        redis_url=url,
        redis_timeout_seconds=2,
        auth_rate_limit_key_prefix=f"easyearn-test-{uuid4().hex}",
        auth_rate_limit_window_seconds=2,
    )
