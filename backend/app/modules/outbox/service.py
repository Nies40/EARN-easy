from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_account_token
from app.integrations.email import OutgoingEmail
from app.modules.auth.tokens import TokenModel
from app.modules.outbox.crypto import EmailPayloadCipher
from app.modules.outbox.models import EmailJob


def enqueue_account_email(
    db: Session,
    settings: Settings,
    model: TokenModel,
    token: str,
    purpose: str,
    message: OutgoingEmail,
) -> EmailJob:
    # Flush, but never commit here: account, token, session, and job are atomic.
    db.flush()
    token_hash = hash_account_token(token)
    account_token = db.get(model, token_hash)
    cipher = EmailPayloadCipher(settings)
    job = EmailJob(
        id=uuid4(),
        user_id=account_token.user_id,
        purpose=purpose,
        token_hash=token_hash,
        expires_at=account_token.expires_at,
        key_id=cipher.active_key_id,
        next_attempt_at=datetime.now(UTC),
    )
    job.encrypted_payload = cipher.encrypt(job, message)
    db.add(job)
    return job
