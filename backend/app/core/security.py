import hashlib
import secrets

import bcrypt

BCRYPT_ROUNDS = 12
# Unknown accounts still perform a bcrypt comparison to reduce timing differences.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-a-real-account-password", bcrypt.gensalt(BCRYPT_ROUNDS))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str | bytes) -> bool:
    encoded_hash = (
        password_hash.encode("ascii") if isinstance(password_hash, str) else password_hash
    )
    return bcrypt.checkpw(password.encode("utf-8"), encoded_hash)


def generate_session_token() -> str:
    return generate_account_token()


def hash_session_token(token: str) -> str:
    return hash_account_token(token)


def generate_account_token() -> str:
    return secrets.token_urlsafe(32)


def hash_account_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
