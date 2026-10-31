from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import Settings
from app.api.dependencies import get_app_settings
from app.modules.referrals import service
from app.modules.referrals.schemas import ReferralResponse, ReferralStatsResponse
from app.modules.users.models import User

router = APIRouter(tags=["Referrals"])


@router.get("/referrals", response_model=ReferralResponse)
def get_referral(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReferralResponse:
    referral = service.get_or_create_referral(db, user.id)
    return ReferralResponse.model_validate(referral)


@router.get("/referrals/stats", response_model=ReferralStatsResponse)
def get_referral_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ReferralStatsResponse:
    stats = service.get_stats(db, user.id, settings)
    return ReferralStatsResponse(**stats)


@router.post("/referrals/track", status_code=202)
def track_referral_click(
    request: Request,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    code = payload.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="Referral code required.")
    referral = service.get_by_code(db, code)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral code not found.")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    service.track_click(db, code, ip, ua)
    return {"status": "tracked"}