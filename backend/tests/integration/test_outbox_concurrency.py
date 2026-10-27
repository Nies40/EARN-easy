from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import func, select, update

from app.modules.auth import service
from app.modules.auth.models import EmailVerificationToken
from app.modules.auth.schemas import SignupRequest
from app.modules.outbox.models import EmailJob
from app.modules.outbox.worker import EmailWorker
from app.modules.users.models import User

pytestmark = pytest.mark.postgres


def create_job(factory, settings, payload):
    with factory() as db:
        user, _, _ = service.register(db, SignupRequest(**payload), settings, None)
        return user.id


def test_two_workers_cannot_claim_the_same_pending_job(pg_factory, settings, signup_payload):
    create_job(pg_factory, settings, signup_payload)
    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)

    workers = [EmailWorker(pg_factory, settings, Sender()) for _ in range(2)]
    barrier = Barrier(2)

    def run(worker):
        barrier.wait(timeout=5)
        return worker.process_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, workers))
    assert sorted(results) == [False, True]
    assert len(messages) == 1
    with pg_factory() as db:
        job = db.scalar(select(EmailJob))
        assert job.status == "sent" and job.encrypted_payload is None and job.attempts == 1


def test_a_stalled_send_is_not_reclaimed_or_allowed_to_block_account_requests(
    pg_factory, settings, signup_payload
):
    user_id = create_job(pg_factory, settings, signup_payload)
    with pg_factory() as db:
        db.execute(
            update(EmailVerificationToken).values(
                created_at=datetime.now(UTC) - timedelta(seconds=120)
            )
        )
        db.commit()
    sending = Event()
    release = Event()

    class SlowSender:
        def send(self, _message):
            sending.set()
            assert release.wait(timeout=5)

    worker = EmailWorker(pg_factory, settings, SlowSender())
    later = datetime.now(UTC) + timedelta(seconds=settings.email_worker_lease_seconds + 5)
    contender = EmailWorker(pg_factory, settings, SlowSender(), clock=lambda: later)

    def resend():
        with pg_factory() as db:
            return service.request_verification(db, db.get(User, user_id), settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        delivery = executor.submit(worker.process_once)
        try:
            assert sending.wait(timeout=5)
            # The lease is logically expired, but SKIP LOCKED skips the live sender.
            assert contender.claim_next() is None
            assert executor.submit(resend).result(timeout=2) is not None
        finally:
            release.set()
        assert delivery.result(timeout=5)
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(EmailJob)) == 2


def test_crash_after_acceptance_recovers_with_the_same_message_id(
    pg_factory, settings, signup_payload
):
    create_job(pg_factory, settings, signup_payload)
    messages = []

    class SimulatedCrash(BaseException):
        pass

    class CrashingSender:
        def send(self, message):
            messages.append(message)
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        EmailWorker(pg_factory, settings, CrashingSender()).process_once()
    with pg_factory() as db:
        job = db.scalar(select(EmailJob))
        assert job.status == "processing" and job.encrypted_payload is not None
        job.leased_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    class Sender:
        def send(self, message):
            messages.append(message)

    assert EmailWorker(pg_factory, settings, Sender()).process_once()
    assert len(messages) == 2
    assert messages[0].message_id == messages[1].message_id
    with pg_factory() as db:
        job = db.scalar(select(EmailJob))
        assert job.status == "sent" and job.encrypted_payload is None
