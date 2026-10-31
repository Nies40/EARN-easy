from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


def normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else value


def validate_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes for bcrypt.")
    return value


FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Username = Annotated[str, StringConstraints(min_length=3, max_length=30, pattern=r"^[a-z0-9_]+$")]
Phone = Annotated[str, StringConstraints(max_length=17, pattern=r"^\+?[0-9]{7,16}$")]
Password = Annotated[
    str, Field(min_length=8, max_length=72), AfterValidator(validate_password_bytes)
]
NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email), Field(max_length=254)]
AccountToken = Annotated[str, Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")]


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: FullName
    email: NormalizedEmail
    password: Password
    username: Username | None = None
    phone: Phone | None = None
    referral_code: str | None = None

    @field_validator("username", "phone", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value):
        return value.strip().lower() or None if isinstance(value, str) else value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)
    ]
    password: Annotated[
        str, Field(min_length=1, max_length=72), AfterValidator(validate_password_bytes)
    ]


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: AccountToken


class PasswordResetRequest(TokenRequest):
    password: Password


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    username: str | None
    phone: str | None
    email_verified: bool
    is_admin: bool
    referral_code: str | None
    created_at: datetime


class AuthResponse(BaseModel):
    message: str
    user: PublicUser


class CurrentUserResponse(BaseModel):
    user: PublicUser


class MessageResponse(BaseModel):
    message: str
