from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router

router = APIRouter(prefix="/api")
router.include_router(auth_router)
router.include_router(dashboard_router)


@router.get("/health", tags=["System"])
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is unavailable.") from error
    return {"status": "ok"}
