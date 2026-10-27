import os

import pytest

from app.ops.acceptance import run_acceptance


@pytest.mark.acceptance
def test_real_api_redis_postgres_smtp_and_worker_processes():
    admin = os.environ.get("TEST_DATABASE_ADMIN_URL")
    redis = os.environ.get("TEST_REDIS_URL")
    if not admin or not redis:
        pytest.skip("Set both TEST_DATABASE_ADMIN_URL and TEST_REDIS_URL for wire acceptance.")
    report = run_acceptance(admin, redis)
    assert report["status"] == "passed"
    assert report["fresh_install"]["passed"]
    assert report["end_to_end"]["smtp_messages"] == 2
    assert report["end_to_end"]["bcrypt_cost"] == 12
    assert report["temporary_database_roles_and_processes_removed"]
