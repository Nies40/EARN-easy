import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    recipient: str = field(repr=False)
    subject: str
    body: str = field(repr=False)
    message_id: str | None = None


class EmailDeliveryError(Exception):
    def __init__(self, message: str = "Email delivery failed.", *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


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
        envelope["Date"] = formatdate(usegmt=True)
        if message.message_id:
            envelope["Message-ID"] = message.message_id
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
        except smtplib.SMTPAuthenticationError as error:
            raise EmailDeliveryError(retryable=True) from error
        except smtplib.SMTPRecipientsRefused as error:
            retryable = any(int(value[0]) < 500 for value in error.recipients.values())
            raise EmailDeliveryError(retryable=retryable) from error
        except smtplib.SMTPResponseException as error:
            raise EmailDeliveryError(retryable=error.smtp_code < 500) from error
        except (OSError, smtplib.SMTPException) as error:
            raise EmailDeliveryError("Email delivery failed.") from error
