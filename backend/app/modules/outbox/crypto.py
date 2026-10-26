import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.integrations.email import OutgoingEmail
from app.modules.outbox.models import EmailJob


class OutboxConfigurationError(ValueError):
    pass


class OutboxKeyUnavailable(Exception):
    pass


class InvalidPayload(Exception):
    pass


class EmailPayloadCipher:
    def __init__(self, settings: Settings):
        if not settings.email_outbox_keys:
            raise OutboxConfigurationError(
                "Set EMAIL_OUTBOX_KEYS before starting the API or worker. "
                "Generate a key with: python -m app.workers.email --generate-key"
            )
        self.keys = {
            hashlib.sha256(value.get_secret_value().encode("ascii")).hexdigest(): Fernet(
                value.get_secret_value().encode("ascii")
            )
            for value in settings.email_outbox_keys
        }
        self.active_key_id = next(iter(self.keys))
        self.sender_domain = str(settings.smtp_from_email).rsplit("@", 1)[1]

    @staticmethod
    def _binding(job: EmailJob) -> dict:
        return {
            "version": 1,
            "job_id": str(job.id),
            "user_id": str(job.user_id),
            "purpose": job.purpose,
            "token_hash": job.token_hash,
        }

    def encrypt(self, job: EmailJob, message: OutgoingEmail) -> str:
        data = dict(
            self._binding(job),
            recipient=message.recipient,
            subject=message.subject,
            body=message.body,
            message_id=f"<{job.id.hex}@{self.sender_domain}>",
        )
        return (
            self.keys[self.active_key_id].encrypt(json.dumps(data).encode("utf-8")).decode("ascii")
        )

    def decrypt(self, job: EmailJob) -> OutgoingEmail:
        key = self.keys.get(job.key_id)
        if key is None:
            raise OutboxKeyUnavailable
        try:
            data = json.loads(key.decrypt(job.encrypted_payload.encode("ascii")))
            if not isinstance(data, dict) or any(
                data.get(name) != value for name, value in self._binding(job).items()
            ):
                raise InvalidPayload
            if any(
                not isinstance(data.get(name), str)
                for name in ("recipient", "subject", "body", "message_id")
            ):
                raise InvalidPayload
            if not data["message_id"].startswith(f"<{job.id.hex}@") or any(
                char in data["message_id"] for char in "\r\n"
            ):
                raise InvalidPayload
            return OutgoingEmail(
                data["recipient"], data["subject"], data["body"], data["message_id"]
            )
        except (InvalidToken, ValueError, TypeError, AttributeError, UnicodeError):
            raise InvalidPayload from None
