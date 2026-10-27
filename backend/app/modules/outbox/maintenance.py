from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken, UserSession
from app.modules.outbox.models import EmailJob
from app.modules.outbox.worker import retire


def cleanup(db: Session, settings: Settings, *, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    batch = settings.email_cleanup_batch_size
    expired = db.scalars(
        select(EmailJob)
        .where(EmailJob.status.in_(("pending", "processing")), EmailJob.expires_at <= now)
        .limit(batch)
        .with_for_update(skip_locked=True)
    ).all()
    for job in expired:
        retire(job, "discarded", now, "expired")
    counts = {"expired_jobs": len(expired)}
    for model, condition in (
        (UserSession, UserSession.expires_at <= now),
        (
            EmailVerificationToken,
            or_(
                EmailVerificationToken.expires_at <= now,
                EmailVerificationToken.used_at.is_not(None),
            ),
        ),
        (
            PasswordResetToken,
            or_(PasswordResetToken.expires_at <= now, PasswordResetToken.used_at.is_not(None)),
        ),
    ):
        query = select(model.token_hash).where(condition)
        if model is not UserSession:
            # Keep the email cooldown intact even for recently consumed/expired tokens.
            query = query.where(
                model.created_at <= now - timedelta(seconds=settings.auth_email_cooldown_seconds)
            )
        keys = db.scalars(query.limit(batch).with_for_update(skip_locked=True)).all()
        if keys:
            db.execute(delete(model).where(model.token_hash.in_(keys)))
        counts[model.__tablename__] = len(keys)
    old_jobs = db.scalars(
        select(EmailJob.id)
        .where(
            EmailJob.completed_at
            <= now - timedelta(seconds=settings.email_outbox_retention_seconds)
        )
        .limit(batch)
        .with_for_update(skip_locked=True)
    ).all()
    if old_jobs:
        db.execute(delete(EmailJob).where(EmailJob.id.in_(old_jobs)))
    counts["old_jobs"] = len(old_jobs)
    db.commit()
    return counts


def status(db: Session) -> dict:
    counts = dict(db.execute(select(EmailJob.status, func.count()).group_by(EmailJob.status)).all())
    errors = dict(
        db.execute(
            select(EmailJob.last_error_code, func.count())
            .where(EmailJob.last_error_code.is_not(None))
            .group_by(EmailJob.last_error_code)
        ).all()
    )
    oldest = db.scalar(select(func.min(EmailJob.created_at)).where(EmailJob.status == "pending"))
    keys = dict(
        db.execute(
            select(EmailJob.key_id, func.count())
            .where(EmailJob.status.in_(("pending", "processing")))
            .group_by(EmailJob.key_id)
        ).all()
    )
    expired_leases = db.scalar(
        select(func.count())
        .select_from(EmailJob)
        .where(EmailJob.status == "processing", EmailJob.leased_until <= datetime.now(UTC))
    )
    return {
        "counts": counts,
        "errors": errors,
        "oldest_pending_at": oldest.isoformat() if oldest else None,
        "active_key_ids": keys,
        "expired_leases": expired_leases,
    }
