import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app.db.permissions import DatabaseRoles, apply_runtime_grants
from app.modules.auth.models import (  # noqa: F401
    EmailVerificationToken,
    PasswordResetToken,
    UserSession,
)
from app.modules.outbox.models import EmailJob  # noqa: F401
from app.modules.users.models import User  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option(
    "sqlalchemy.url", get_settings().database_url.get_secret_value().replace("%", "%%")
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        hide_parameters=True,
    )
    with connectable.connect() as connection:
        prefix = os.environ.get("DATABASE_ROLE_PREFIX")
        if prefix:
            roles = DatabaseRoles(prefix)
            quoted = connection.dialect.identifier_preparer.quote(roles.name("owner"))
            connection.exec_driver_sql("SET ROLE " + quoted)
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        if prefix:
            with connection.begin():
                apply_runtime_grants(connection.connection.driver_connection, roles)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
