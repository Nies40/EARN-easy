import argparse
import json
import logging
import signal
from threading import Event
from time import monotonic

from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.integrations.email import SMTPEmailSender
from app.modules.outbox.maintenance import cleanup, status
from app.modules.outbox.worker import EmailWorker

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable account-email worker and maintenance.")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument(
        "--generate-key", action="store_true", help="Print a new secret JSON key ring."
    )
    commands.add_argument("--once", action="store_true", help="Process at most one due job.")
    commands.add_argument(
        "--status", action="store_true", help="Print aggregate queue metadata only."
    )
    commands.add_argument(
        "--cleanup", action="store_true", help="Run one bounded maintenance batch."
    )
    args = parser.parse_args(argv)
    if args.generate_key:
        print(json.dumps([Fernet.generate_key().decode("ascii")]))
        return 0
    settings = get_settings()
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        if args.status or args.cleanup:
            with factory() as db:
                print(json.dumps(status(db) if args.status else cleanup(db, settings)))
            return 0
        worker = EmailWorker(factory, settings, SMTPEmailSender(settings))
        if args.once:
            worker.process_once()
            return 0
        stop = Event()
        previous = {
            sig: signal.signal(sig, lambda _signal, _frame: stop.set())
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        next_cleanup = 0.0
        try:
            while not stop.is_set():
                try:
                    if monotonic() >= next_cleanup:
                        with factory() as db:
                            cleanup(db, settings)
                        next_cleanup = monotonic() + settings.email_cleanup_interval_seconds
                    if not worker.process_once():
                        stop.wait(settings.email_worker_poll_seconds)
                except SQLAlchemyError as error:
                    logger.error(
                        "Email worker database operation failed (%s).", type(error).__name__
                    )
                    stop.wait(settings.email_worker_poll_seconds)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
