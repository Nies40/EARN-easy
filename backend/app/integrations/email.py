import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    recipient: str = field(repr=False)
    subject: str
    body: str = field(repr=False)


class EmailDeliveryError(Exception):
    pass


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


class SMTPEmailSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, message: OutgoingEmail) -> None:
        envelope = EmailMessage()
        envelope["From"] = str(self.settings.smtp_from_email)
        envelope["To"] = message.recipient
        envelope["Subject"] = message.subject
        envelope.set_content(message.body)
        options = {
            "host": self.settings.smtp_host,
            "port": self.settings.smtp_port,
            "timeout": self.settings.smtp_timeout_seconds,
        }
        try:
            if self.settings.smtp_tls_mode == "ssl":
                connection = smtplib.SMTP_SSL(**options, context=ssl.create_default_context())
            else:
                connection = smtplib.SMTP(**options)
            with connection as smtp:
                if self.settings.smtp_tls_mode == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if self.settings.smtp_username:
                    smtp.login(
                        self.settings.smtp_username,
                        self.settings.smtp_password.get_secret_value(),
                    )
                smtp.send_message(envelope)
        except (OSError, smtplib.SMTPException) as error:
            raise EmailDeliveryError("Email delivery failed.") from error


def deliver_email(sender: EmailSender, message: OutgoingEmail) -> None:
    """Best-effort background delivery; do not log addresses, bodies, or token links."""
    try:
        sender.send(message)
    except EmailDeliveryError as error:
        logger.error(
            "Account email delivery failed (%s). A new request may be needed after the cooldown.",
            type(error.__cause__ or error).__name__,
        )
