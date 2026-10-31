import secrets
import string
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.referrals.models import Referral, ReferralClick


def _gen_code() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def get_or_create_referral(db: Session, user_id: UUID) -> Referral:
    referral = db.scalar(
        select(Referral).where(Referral.referrer_id == user_id).limit(1)
    )
    if referral is None:
        code = _gen_code()
        while db.scalar(select(Referral).where(Referral.referral_code == code)):
            code = _gen_code()
        referral = Referral(referrer_id=user_id, referral_code=code)
        db.add(referral)
        db.commit()
        db.refresh(referral)
    return referral


def get_by_code(db: Session, code: str) -> Referral | None:
    return db.scalar(select(Referral).where(Referral.referral_code == code))


def track_click(db: Session, code: str, ip: str | None, user_agent: str | None) -> None:
    click = ReferralClick(referral_code=code, ip_address=ip, user_agent=user_agent[:500] if user_agent else None)
    db.add(click)
    db.commit()


def get_stats(db: Session, user_id: UUID, settings: Settings) -> dict:
    referral = get_or_create_referral(db, user_id)
    total = db.scalar(
        select(func.count(Referral.id)).where(Referral.referrer_id == user_id)
    ) or 0
    activated = db.scalar(
        select(func.count(Referral.id)).where(
            Referral.referrer_id == user_id, Referral.status == "activated"
        )
    ) or 0
    # For the dashboard, we also count how many users signed up using this code
    # (the referred_id column). This is a separate metric from activation.
    referred_count = db.scalar(
        select(func.count(Referral.id)).where(
            Referral.referrer_id == user_id, Referral.referred_id.is_not(None)
        )
    ) or 0
    total_bonus = db.scalar(
        select(func.coalesce(func.sum(Referral.bonus_amount), 0)).where(
            Referral.referrer_id == user_id, Referral.status == "activated"
        )
    ) or 0
    link = f"{settings.frontend_url}/r/{referral.referral_code}"
    return {
        "total_referrals": referred_count,
        "activated_referrals": activated,
        "pending_referrals": (referred_count - activated) if referred_count > activated else 0,
        "total_bonus_earned": total_bonus,
        "referral_code": referral.referral_code,
        "referral_link": link,
    }


def get_referral_trend(db: Session, user_id: UUID) -> list[dict]:
    """Monthly referral count for the last 6 months."""
    rows = db.execute(
        select(
            func.to_char(Referral.created_at, "YYYY-MM").label("month"),
            func.count(Referral.id).label("count"),
        )
        .where(Referral.referrer_id == user_id)
        .group_by("month")
        .order_by("month")
    ).all()
    return [{"month": r.month, "count": r.count} for r in rows]