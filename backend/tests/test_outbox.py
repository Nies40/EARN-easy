import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.integrations.email import EmailDeliveryError
from app.main import create_app
from app.modules.auth.models import EmailVerificationToken, UserSession
from app.modules.outbox.crypto import EmailPayloadCipher, InvalidPayload, OutboxConfigurationError
from app.modules.outbox.maintenance import cleanup, status
from app.modules.outbox.models import EmailJob
from app.modules.outbox.worker import EmailWorker, as_utc
from app.modules.users.models import User


def job_from(db):
    db.expire_all()
    return db.scalar(select(EmailJob).order_by(EmailJob.next_attempt_at.desc()))


def test_request_only_enqueues_encrypted_email(client, db, signup_payload, email_sender, settings):
    response = client.post("/api/signup", json=signup_payload)
    assert response.status_code == 201
    assert email_sender.messages == []
    job = job_from(db)
    assert job.status == "pending" and job.attempts == 0
    message = EmailPayloadCipher(settings).decrypt(job)
    assert message.recipient == signup_payload["email"]
    assert message.recipient not in job.encrypted_payload
    assert message.body not in job.encrypted_payload
    assert "token=" not in job.encrypted_payload
    assert "encrypted_payload" not in response.text
    email_sender.deliver_pending()
    job = job_from(db)
    assert job.status == "sent" and job.encrypted_payload is None
    assert job.completed_at is not None and job.lease_id is None
    assert email_sender.messages[0].message_id == message.message_id


def test_outbox_failure_rolls_back_account_token_and_session(
    client, db, signup_payload, monkeypatch
):
    def broken(*_args):
        raise RuntimeError("encryption failed")

    monkeypatch.setattr(EmailPayloadCipher, "encrypt", broken)
    with pytest.raises(RuntimeError, match="encryption failed"):
        client.post("/api/signup", json=signup_payload)
    db.rollback()  # The test dependency shares a session; real request contexts close it.
    for model in (User, UserSession, EmailVerificationToken, EmailJob):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_api_refuses_to_start_without_explicit_keys(settings, rate_limiter):
    missing = settings.model_copy(update={"email_outbox_keys": []})
    with pytest.raises(OutboxConfigurationError, match="EMAIL_OUTBOX_KEYS"):
        with TestClient(create_app(missing, rate_limiter=rate_limiter)):
            pass


@pytest.mark.parametrize("keys", [["bad-key"], ["é" * 44]])
def test_malformed_key_rings_are_rejected(keys):
    with pytest.raises(ValueError, match="Fernet"):
        Settings(_env_file=None, email_outbox_keys=keys)


def test_key_ring_is_redacted_and_rejects_duplicates(settings):
    secret = settings.email_outbox_keys[0].get_secret_value()
    assert secret not in repr(settings)
    with pytest.raises(ValueError, match="duplicate"):
        Settings(_env_file=None, email_outbox_keys=[secret, secret])


def test_transient_failure_retries_with_stable_message_id(
    client, db, signup_payload, email_sender, monkeypatch
):
    client.post("/api/signup", json=signup_payload)
    attempted = []
    original_send = email_sender.send

    def fail_once(message):
        attempted.append(message.message_id)
        if len(attempted) == 1:
            raise EmailDeliveryError()
        original_send(message)

    monkeypatch.setattr(email_sender, "send", fail_once)
    email_sender.deliver_pending()
    job = job_from(db)
    assert job.status == "pending" and job.attempts == 1
    assert job.encrypted_payload is not None
    assert 29 <= (as_utc(job.next_attempt_at) - datetime.now(UTC)).total_seconds() <= 34
    db.execute(update(EmailJob).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    email_sender.deliver_pending()
    job = job_from(db)
    assert job.status == "sent" and job.attempts == 2
    assert len(email_sender.messages) == 1
    assert len(set(attempted)) == 1


def test_permanent_failure_and_retry_exhaustion_erase_payload(
    client, db, signup_payload, email_sender, monkeypatch, settings
):
    client.post("/api/signup", json=signup_payload)

    def permanent_failure(_message):
        raise EmailDeliveryError(retryable=False)

    monkeypatch.setattr(email_sender, "send", permanent_failure)
    email_sender.deliver_pending()
    assert job_from(db).status == "failed"
    assert job_from(db).encrypted_payload is None
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    db.execute(
        update(EmailJob)
        .where(EmailJob.status == "pending")
        .values(attempts=settings.email_worker_max_attempts)
    )
    db.commit()
    email_sender.deliver_pending()
    assert job_from(db).status == "failed"
    assert job_from(db).last_error_code == "attempts_exhausted"


@pytest.mark.parametrize("change", ["expire", "consume", "supersede", "recipient", "corrupt"])
def test_worker_discards_invalid_jobs_without_sending(
    client, db, signup_payload, email_sender, change
):
    client.post("/api/signup", json=signup_payload)
    job = job_from(db)
    if change == "expire":
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "consume":
        db.execute(update(EmailVerificationToken).values(used_at=datetime.now(UTC)))
    elif change == "supersede":
        db.delete(db.get(EmailVerificationToken, job.token_hash))
    elif change == "recipient":
        db.scalar(select(User)).email = "changed@example.com"
    else:
        job.encrypted_payload = "not-authentic-ciphertext"
    db.commit()
    email_sender.deliver_pending()
    assert job_from(db).status in ("failed", "discarded")
    assert job_from(db).encrypted_payload is None
    assert email_sender.messages == []


def test_key_rotation_reads_old_jobs_and_missing_key_never_destroys_them(
    client, db, signup_payload, email_sender, settings
):
    client.post("/api/signup", json=signup_payload)
    old_job = job_from(db)
    new_key = Fernet.generate_key().decode("ascii")
    wrong_settings = Settings(_env_file=None, email_outbox_keys=[new_key])
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    wrong = EmailWorker(factory, wrong_settings, email_sender)
    assert wrong.process_once()
    job = job_from(db)
    assert job.status == "pending" and job.attempts == 0
    assert job.encrypted_payload is not None and job.last_error_code == "key_unavailable"
    ring = Settings(
        _env_file=None,
        email_outbox_keys=[new_key, settings.email_outbox_keys[0].get_secret_value()],
    )
    assert EmailPayloadCipher(ring).decrypt(old_job).recipient == signup_payload["email"]
    db.execute(update(EmailJob).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert EmailWorker(factory, ring, email_sender).process_once()
    assert job_from(db).status == "sent"


def test_abandoned_claim_is_recovered_and_old_claim_cannot_send(
    client, db, signup_payload, email_sender
):
    client.post("/api/signup", json=signup_payload)
    worker = email_sender.worker
    old_claim = worker.claim_next()
    assert worker.claim_next() is None
    db.execute(update(EmailJob).values(leased_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    recovered = worker.claim_next()
    assert recovered.lease_id != old_claim.lease_id
    worker.deliver(old_claim)
    assert email_sender.messages == []
    worker.deliver(recovered)
    assert len(email_sender.messages) == 1
    assert job_from(db).attempts == 2


def test_cleanup_preserves_live_sessions_and_email_cooldowns(client, db, signup_payload, settings):
    client.post("/api/signup", json=signup_payload)
    now = datetime.now(UTC)
    token = db.scalar(select(EmailVerificationToken))
    token.used_at = now
    db.commit()
    cleanup(db, settings, now=now)
    assert db.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
    assert db.scalar(select(func.count()).select_from(UserSession)) == 1
    db.execute(update(UserSession).values(expires_at=now - timedelta(seconds=1)))
    db.execute(update(EmailVerificationToken).values(created_at=now - timedelta(seconds=120)))
    db.execute(update(EmailJob).values(expires_at=now - timedelta(seconds=1)))
    db.commit()
    counts = cleanup(db, settings, now=now)
    assert counts["user_sessions"] == counts["email_verification_tokens"] == 1
    assert job_from(db).status == "discarded" and job_from(db).encrypted_payload is None
    summary = json.dumps(status(db))
    assert signup_payload["email"] not in summary and "token=" not in summary


def test_ciphertext_is_bound_to_its_job_metadata(client, db, signup_payload, settings):
    client.post("/api/signup", json=signup_payload)
    first = job_from(db)
    encrypted = first.encrypted_payload
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    second = job_from(db)
    second.encrypted_payload = encrypted
    db.commit()
    with pytest.raises(InvalidPayload):
        EmailPayloadCipher(settings).decrypt(second)


def test_key_generator_does_not_need_configured_services(capsys):
    from app.workers.email import main

    assert main(["--generate-key"]) == 0
    keys = json.loads(capsys.readouterr().out)
    assert len(keys) == 1
    Fernet(keys[0].encode("ascii"))
