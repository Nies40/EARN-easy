import smtplib
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.email import EmailDeliveryError, OutgoingEmail, SMTPEmailSender


def test_local_smtp_uses_mailpit_without_authentication(monkeypatch, settings):
    connection = MagicMock()
    smtp = connection.__enter__.return_value
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", factory)
    SMTPEmailSender(settings).send(OutgoingEmail("jane@example.com", "Subject", "Body"))
    factory.assert_called_once_with(host="localhost", port=1025, timeout=10)
    smtp.starttls.assert_not_called()
    smtp.login.assert_not_called()
    envelope = smtp.send_message.call_args.args[0]
    assert envelope["To"] == "jane@example.com"
    assert envelope["From"] == "no-reply@example.com"
    assert envelope.get_content() == "Body\n"


@pytest.mark.parametrize("mode", ["starttls", "ssl"])
def test_secure_smtp_modes_and_credentials(monkeypatch, mode):
    settings = Settings(
        _env_file=None,
        smtp_tls_mode=mode,
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
    )
    connection = MagicMock()
    smtp = connection.__enter__.return_value
    factory = MagicMock(return_value=connection)
    target = "SMTP_SSL" if mode == "ssl" else "SMTP"
    monkeypatch.setattr(f"app.integrations.email.smtplib.{target}", factory)
    SMTPEmailSender(settings).send(OutgoingEmail("jane@example.com", "Subject", "Body"))
    smtp.login.assert_called_once_with("smtp-user", "smtp-secret")
    if mode == "starttls":
        smtp.starttls.assert_called_once()
    else:
        assert "context" in factory.call_args.kwargs
        smtp.starttls.assert_not_called()
    assert "smtp-secret" not in repr(settings)


def test_smtp_errors_are_wrapped_without_including_message_content(monkeypatch, settings):
    monkeypatch.setattr(
        "app.integrations.email.smtplib.SMTP", MagicMock(side_effect=OSError("connection failed"))
    )
    with pytest.raises(EmailDeliveryError, match="Email delivery failed"):
        SMTPEmailSender(settings).send(OutgoingEmail("jane@example.com", "Subject", "secret-token"))


@pytest.mark.parametrize("code", [450, 550])
def test_smtp_response_classification_controls_retries(monkeypatch, settings, code):
    connection = MagicMock()
    connection.__enter__.return_value.send_message.side_effect = smtplib.SMTPDataError(
        code, b"secret"
    )
    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", MagicMock(return_value=connection))
    with pytest.raises(EmailDeliveryError) as caught:
        SMTPEmailSender(settings).send(OutgoingEmail("jane@example.com", "Subject", "Body"))
    assert caught.value.retryable is (code < 500)
    assert "secret" not in str(caught.value)


def test_delivery_failure_does_not_log_token_address_or_provider_response(
    client, signup_payload, email_sender, monkeypatch, caplog
):
    def unavailable(_message):
        raise smtplib.SMTPDataError(500, b"provider-response-with-a-secret-token")

    monkeypatch.setattr(email_sender, "send", unavailable)
    client.post("/api/signup", json=signup_payload)
    email_sender.deliver_pending()
    assert "Outbox delivery failed" in caplog.text
    assert "secret-token" not in caplog.text
    assert "private@example.com" not in caplog.text


def test_signup_remains_available_if_smtp_is_down(
    client, signup_payload, email_sender, monkeypatch
):
    def unavailable(_message):
        raise EmailDeliveryError("Email delivery failed.")

    monkeypatch.setattr(email_sender, "send", unavailable)
    assert client.post("/api/signup", json=signup_payload).status_code == 201
    email_sender.deliver_pending()
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/dashboard").status_code == 403


def test_smtp_credentials_must_be_paired():
    with pytest.raises(ValidationError, match="both SMTP_USERNAME and SMTP_PASSWORD"):
        Settings(_env_file=None, smtp_username="smtp-user")


def test_production_rejects_unencrypted_smtp():
    with pytest.raises(ValidationError, match="SMTP_TLS_MODE"):
        Settings(_env_file=None, app_env="production", app_url="https://example.com")


def test_production_requires_a_non_placeholder_sender():
    with pytest.raises(ValidationError, match="SMTP_FROM_EMAIL"):
        Settings(
            _env_file=None, app_env="production", app_url="https://example.com", smtp_tls_mode="ssl"
        )


def test_sender_delivers_a_message_over_local_smtp(settings):
    messages = []

    class SMTPHandler(StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 localhost test SMTP\r\n")
            while line := self.rfile.readline():
                command = line.split(b" ", 1)[0].strip().upper()
                if command == b"DATA":
                    self.wfile.write(b"354 End with a dot\r\n")
                    data = bytearray()
                    while chunk := self.rfile.readline():
                        if chunk == b".\r\n":
                            break
                        data.extend(chunk)
                    messages.append(bytes(data))
                    self.wfile.write(b"250 Accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 localhost\r\n")

    with TCPServer(("127.0.0.1", 0), SMTPHandler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            local = settings.model_copy(
                update={"smtp_host": "127.0.0.1", "smtp_port": server.server_address[1]}
            )
            SMTPEmailSender(local).send(OutgoingEmail("jane@example.com", "Subject", "Test body"))
        finally:
            server.shutdown()
            thread.join(timeout=2)
    assert len(messages) == 1
    assert b"To: jane@example.com" in messages[0]
    assert b"Test body" in messages[0]
