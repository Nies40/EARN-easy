import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.email import EmailDeliveryError, EmailSender
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken
from app.modules.outbox.crypto import EmailPayloadCipher, InvalidPayload, OutboxKeyUnavailable
from app.modules.outbox.models import EmailJob
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def retire(job: EmailJob, status: str, now: datetime, code: str | None = None) -> None:
    job.status = status
    job.encrypted_payload = None
    job.completed_at = now
    job.lease_id = None
    job.leased_until = None
    job.last_error_code = code


@dataclass(frozen=True, slots=True)
class Claim:
    job_id: UUID
    lease_id: UUID | None


class EmailWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        sender: EmailSender,
        *,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.factory = session_factory
        self.settings = settings
        self.sender = sender
        self.cipher = EmailPayloadCipher(settings)
        self.clock = clock

    def claim_next(self) -> Claim | None:
        now = self.clock()
        with self.factory() as db, db.begin():
            job = db.scalar(
                select(EmailJob)
                .where(
                    or_(
                        and_(EmailJob.status == "pending", EmailJob.next_attempt_at <= now),
                        and_(EmailJob.status == "processing", EmailJob.leased_until <= now),
                    )
                )
                .order_by(EmailJob.next_attempt_at, EmailJob.created_at, EmailJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            if as_utc(job.expires_at) <= now:
                retire(job, "discarded", now, "expired")
                return Claim(job.id, None)
            if job.attempts >= self.settings.email_worker_max_attempts:
                retire(job, "failed", now, "attempts_exhausted")
                return Claim(job.id, None)
            job.status = "processing"
            job.attempts += 1
            job.lease_id = uuid4()
            job.leased_until = now + timedelta(seconds=self.settings.email_worker_lease_seconds)
            return Claim(job.id, job.lease_id)

    def _retry(self, job: EmailJob, now: datetime, code: str, *, missing_key: bool = False):
        if missing_key:
            # A misconfigured key ring must not destroy recoverable pending messages.
            job.attempts -= 1
        base = min(
            self.settings.email_retry_max_seconds,
            self.settings.email_retry_base_seconds * 2 ** max(0, job.attempts - 1),
        )
        jitter = secrets.randbelow(max(1, base // 10 + 1))
        delay = min(self.settings.email_retry_max_seconds, base + jitter)
        job.status = "pending"
        job.lease_id = None
        job.leased_until = None
        job.next_attempt_at = now + timedelta(seconds=delay)
        job.last_error_code = code

    def deliver(self, claim: Claim) -> None:
        if claim.lease_id is None:
            return
        with self.factory() as db, db.begin():
            # Hold only the job lock across SMTP. Other workers skip it even if its
            # lease expires. Auth/token rows are never locked by the delivery worker.
            job = db.scalar(
                select(EmailJob)
                .where(
                    EmailJob.id == claim.job_id,
                    EmailJob.lease_id == claim.lease_id,
                    EmailJob.status == "processing",
                )
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return
            now = self.clock()
            model = EmailVerificationToken if job.purpose == "verification" else PasswordResetToken
            token = db.get(model, job.token_hash)
            user = db.execute(
                select(User.id, User.email, User.email_verified_at).where(User.id == job.user_id)
            ).first()
            if (
                as_utc(job.expires_at) <= now
                or token is None
                or token.used_at is not None
                or as_utc(token.expires_at) <= now
                or token.user_id != job.user_id
                or user is None
                or (job.purpose == "verification" and user.email_verified_at is not None)
            ):
                retire(job, "discarded", now, "token_inactive")
                return
            try:
                message = self.cipher.decrypt(job)
            except OutboxKeyUnavailable:
                self._retry(job, now, "key_unavailable", missing_key=True)
                logger.error("Outbox key unavailable; restore key ring. job_id=%s", job.id)
                return
            except InvalidPayload:
                retire(job, "failed", now, "payload_invalid")
                logger.error("Outbox payload failed integrity validation. job_id=%s", job.id)
                return
            if message.recipient != user.email:
                retire(job, "discarded", now, "recipient_changed")
                return
            code = None
            retryable = True
            try:
                self.sender.send(message)
            except EmailDeliveryError as error:
                retryable = error.retryable
                code = "smtp_transient" if retryable else "smtp_permanent"
            except Exception:
                # No exception bodies: SMTP/provider errors can contain bearer links.
                code = "sender_error"
            finished = self.clock()
            if code is None:
                retire(job, "sent", finished)
            else:
                logger.warning("Outbox delivery failed. job_id=%s code=%s", job.id, code)
                if as_utc(job.expires_at) <= finished:
                    retire(job, "discarded", finished, "expired")
                elif not retryable or job.attempts >= self.settings.email_worker_max_attempts:
                    retire(job, "failed", finished, code)
                else:
                    self._retry(job, finished, code)

    def process_once(self) -> bool:
        claim = self.claim_next()
        if claim is None:
            return False
        self.deliver(claim)
        return True
