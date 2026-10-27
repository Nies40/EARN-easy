from urllib.parse import urlencode

from app.core.config import Settings
from app.integrations.email import OutgoingEmail


def verification_email(recipient: str, token: str, settings: Settings) -> OutgoingEmail:
    # Fragments keep tokens out of HTTP access logs and referrer URLs. The frontend
    # must explicitly POST the token; visiting a link must never consume it.
    link = f"{str(settings.app_url).rstrip('/')}/verify-email#{urlencode({'token': token})}"
    return OutgoingEmail(
        recipient=recipient,
        subject="Verify your Easyearn email",
        body=(
            "Confirm your email address to unlock your Easyearn dashboard.\n\n"
            f"{link}\n\n"
            f"This link expires {settings.email_verification_ttl_seconds // 60} minutes "
            "after it was requested and can be used once. "
            "Requesting a new link replaces this one.\n"
            "If you did not create this account, you can ignore this email.\n"
        ),
    )


def password_reset_email(recipient: str, token: str, settings: Settings) -> OutgoingEmail:
    link = f"{str(settings.app_url).rstrip('/')}/reset-password#{urlencode({'token': token})}"
    return OutgoingEmail(
        recipient=recipient,
        subject="Reset your Easyearn password",
        body=(
            "A password reset was requested for your Easyearn account.\n\n"
            f"{link}\n\n"
            f"This link expires {settings.password_reset_ttl_seconds // 60} minutes "
            "after it was requested and can be used once. "
            "Requesting a new link replaces this one.\n"
            "Your password will not change until you submit a new one. "
            "If you did not request this, ignore this email.\n"
        ),
    )
