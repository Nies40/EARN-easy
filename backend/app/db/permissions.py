import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import Engine

APP_TABLES = (
    "users",
    "user_sessions",
    "email_verification_tokens",
    "password_reset_tokens",
    "email_outbox",
)
ALL_TABLES = (*APP_TABLES, "alembic_version")


class DatabasePermissionError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseRoles:
    prefix: str = "easyearn"

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,35}", self.prefix):
            raise DatabasePermissionError("Use a lowercase role prefix of at most 36 characters.")

    def name(self, kind: str) -> str:
        if kind not in ("owner", "migrator", "api", "worker", "backup"):
            raise DatabasePermissionError("Unknown database role kind.")
        return f"{self.prefix}_{kind}"

    def marker(self, kind: str) -> str:
        return f"Easyearn managed role v1:{self.prefix}:{kind}"


def assert_dedicated_database(db: psycopg.Connection, database: str) -> set[str]:
    if database in ("postgres", "template0", "template1"):
        raise DatabasePermissionError("Refusing to provision a maintenance/template database.")
    if db.execute("SELECT current_database()").fetchone()[0] != database:
        raise DatabasePermissionError(
            "The explicit database name must match the connected database."
        )
    objects = db.execute("""
        SELECT n.nspname, c.relname, c.relkind
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d
                          WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                            AND d.deptype = 'e')
    """).fetchall()
    if any(
        schema != "public" or name not in ALL_TABLES or kind != "r"
        for schema, name, kind in objects
    ):
        raise DatabasePermissionError("Use a dedicated database with no unrelated tables or views.")
    functions = db.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid
                              AND d.classid = 'pg_proc'::regclass AND d.deptype = 'e')
        )
    """).fetchone()[0]
    if functions:
        raise DatabasePermissionError("Use a dedicated database without unrelated functions.")
    return {name for _schema, name, _kind in objects}


def validate_application_schema(db: psycopg.Connection) -> None:
    from app.db.base import Base
    from app.modules.auth import models as _auth_models  # noqa: F401
    from app.modules.outbox.models import EmailJob as _email_job  # noqa: F401
    from app.modules.users.models import User as _user  # noqa: F401

    tables = assert_dedicated_database(db, db.execute("SELECT current_database()").fetchone()[0])
    if tables != set(ALL_TABLES):
        raise DatabasePermissionError("Required application tables are missing.")
    for table in tables:
        expected = (
            {"version_num"}
            if table == "alembic_version"
            else set(Base.metadata.tables[table].columns.keys())
        )
        actual = {
            row[0]
            for row in db.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall()
        }
        if actual != expected:
            raise DatabasePermissionError("Application table columns do not match this release.")
    head = ScriptDirectory(
        str(Path(__file__).resolve().parents[2] / "migrations")
    ).get_current_head()
    if db.execute("SELECT version_num FROM public.alembic_version").fetchall() != [(head,)]:
        raise DatabasePermissionError(
            "Backup/restore schema must match the current migration head."
        )


def apply_runtime_grants(db: psycopg.Connection, roles: DatabaseRoles) -> None:
    for kind in ("owner", "migrator", "api", "worker", "backup"):
        marker = db.execute(
            "SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s",
            (roles.name(kind),),
        ).fetchone()
        if marker is None or marker[0] != roles.marker(kind):
            raise DatabasePermissionError("Refusing to change grants on unmanaged/missing roles.")
    tables = db.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    available = {row[0] for row in tables}
    for name in ALL_TABLES:
        if name not in available:
            continue
        table = sql.Identifier("public", name)
        columns = db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (name,),
        ).fetchall()
        column_list = sql.SQL(", ").join(sql.Identifier(row[0]) for row in columns)
        db.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM PUBLIC").format(table))
        for kind in ("api", "worker", "backup"):
            db.execute(
                sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(
                    table, sql.Identifier(roles.name(kind))
                )
            )
            db.execute(
                sql.SQL("REVOKE ALL ({}) ON TABLE {} FROM {}").format(
                    column_list, table, sql.Identifier(roles.name(kind))
                )
            )
        db.execute(sql.SQL("REVOKE ALL ({}) ON TABLE {} FROM PUBLIC").format(column_list, table))
        db.execute(
            sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
                table, sql.Identifier(roles.name("backup"))
            )
        )
    api = sql.Identifier(roles.name("api"))
    worker = sql.Identifier(roles.name("worker"))
    grants = {
        "users": "SELECT, INSERT, UPDATE",
        "user_sessions": "SELECT, INSERT, DELETE",
        "email_verification_tokens": "SELECT, INSERT, UPDATE, DELETE",
        "password_reset_tokens": "SELECT, INSERT, UPDATE, DELETE",
        "email_outbox": "INSERT",
    }
    for table, privileges in grants.items():
        if table in available:
            db.execute(
                sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                    sql.SQL(privileges), sql.Identifier("public", table), api
                )
            )
    if "email_outbox" in available:
        db.execute(
            sql.SQL("GRANT SELECT (id, created_at) ON public.email_outbox TO {}").format(api)
        )
        db.execute(
            sql.SQL("GRANT SELECT, UPDATE, DELETE ON public.email_outbox TO {}").format(worker)
        )
    if "users" in available:
        db.execute(
            sql.SQL("GRANT SELECT (id, email, email_verified_at) ON public.users TO {}").format(
                worker
            )
        )
    for name in ("user_sessions", "email_verification_tokens", "password_reset_tokens"):
        if name in available:
            table = sql.Identifier("public", name)
            db.execute(sql.SQL("GRANT SELECT, DELETE ON TABLE {} TO {}").format(table, worker))
            # PostgreSQL requires UPDATE on at least one column for FOR UPDATE.
            # Grant metadata only, never token hashes, expiry, user IDs, or password hashes.
            db.execute(sql.SQL("GRANT UPDATE (created_at) ON TABLE {} TO {}").format(table, worker))


def provision_roles(
    db: psycopg.Connection,
    database: str,
    roles: DatabaseRoles,
    passwords: dict[str, str],
    *,
    adopt_existing: bool = False,
) -> dict[str, str]:
    available = assert_dedicated_database(db, database)
    if available and not adopt_existing:
        raise DatabasePermissionError("Existing tables require explicit --adopt-existing approval.")
    if available:
        from app.db.base import Base
        from app.modules.auth import models as _auth_models  # noqa: F401
        from app.modules.outbox.models import EmailJob as _email_job  # noqa: F401
        from app.modules.users.models import User as _user  # noqa: F401

        for table in available:
            expected = (
                {"version_num"}
                if table == "alembic_version"
                else set(Base.metadata.tables[table].columns.keys())
            )
            actual = {
                row[0]
                for row in db.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                ).fetchall()
            }
            if actual != expected:
                raise DatabasePermissionError(
                    "Existing table shapes do not match this application's models."
                )
    kinds = ("owner", "migrator", "api", "worker", "backup")
    existing = db.execute(
        "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
        ([roles.name(kind) for kind in kinds],),
    ).fetchall()
    if existing:
        raise DatabasePermissionError(
            "Role names already exist; no passwords or roles were changed."
        )
    for kind in kinds[1:]:
        value = passwords.get(kind, "")
        if not 24 <= len(value.encode("utf-8")) <= 128 or value.startswith("replace-"):
            raise DatabasePermissionError(
                "Supply distinct generated role passwords of 24–128 bytes."
            )
    if len(set(passwords.values())) != 4:
        raise DatabasePermissionError("Use a different password for each login role.")
    for kind in kinds:
        role = roles.name(kind)
        login = sql.SQL("NOLOGIN") if kind == "owner" else sql.SQL("LOGIN")
        db.execute(
            sql.SQL(
                "CREATE ROLE {} {} NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(role), login)
        )
        if kind != "owner":
            verifier = db.pgconn.encrypt_password(
                passwords[kind].encode("utf-8"), role.encode("utf-8"), b"scram-sha-256"
            ).decode("ascii")
            db.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(verifier)
                )
            )
        db.execute(
            sql.SQL("COMMENT ON ROLE {} IS {}").format(
                sql.Identifier(role), sql.Literal(roles.marker(kind))
            )
        )
    db.execute(
        sql.SQL("GRANT {} TO {}").format(
            sql.Identifier(roles.name("owner")), sql.Identifier(roles.name("migrator"))
        )
    )
    db.execute(
        sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(
            sql.Identifier(roles.name("backup"))
        )
    )
    db.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
    db.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    db.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
            sql.Identifier(roles.name("owner"))
        )
    )
    for kind in kinds[1:]:
        db.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(roles.name(kind))
            )
        )
        db.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(roles.name(kind)))
        )
    for table in available:
        db.execute(
            sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                sql.Identifier("public", table), sql.Identifier(roles.name("owner"))
            )
        )
    apply_runtime_grants(db, roles)
    return {kind: roles.name(kind) for kind in kinds}


def check_runtime_database_role(engine: Engine, kind: str) -> None:
    if kind not in ("api", "worker"):
        raise DatabasePermissionError("Unknown runtime process kind.")
    with engine.connect() as connection:
        row = connection.exec_driver_sql("""
            SELECT r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
                   OR r.rolbypassrls
                   OR has_database_privilege(current_database(), 'CREATE')
                   OR has_database_privilege(current_database(), 'TEMP')
                   OR has_schema_privilege('public', 'CREATE')
            FROM pg_roles r WHERE r.rolname = current_user
        """).scalar_one()
        if row:
            raise DatabasePermissionError(
                "Runtime database roles must not have admin or DDL privileges."
            )
        ownership = connection.exec_driver_sql("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                  AND pg_has_role(current_user, c.relowner, 'MEMBER')
            )
        """).scalar_one()
        if ownership:
            raise DatabasePermissionError(
                "Runtime roles must not own or inherit application objects."
            )
        membership = connection.exec_driver_sql("""
            SELECT EXISTS (SELECT 1 FROM pg_auth_members
                           WHERE member = (SELECT oid FROM pg_roles WHERE rolname = current_user))
        """).scalar_one()
        if membership:
            raise DatabasePermissionError(
                "Runtime roles must not have memberships in other database roles."
            )
        forbidden = "INSERT,UPDATE,DELETE" if kind == "worker" else "DELETE"
        result = connection.exec_driver_sql(
            "SELECT has_table_privilege('public.users', %s)", (forbidden,)
        ).scalar_one()
        if result or (
            kind == "worker"
            and connection.exec_driver_sql("""
                SELECT has_column_privilege('public.users', 'password_hash', 'SELECT')
                       OR has_any_column_privilege('public.users', 'INSERT,UPDATE')
            """).scalar_one()
        ):
            raise DatabasePermissionError("Runtime role has excessive user-table privileges.")
        required = (
            "SELECT has_table_privilege('public.users', 'INSERT') "
            "AND has_column_privilege('public.users', 'password_hash', 'SELECT') "
            "AND has_table_privilege('public.email_outbox', 'INSERT')"
            if kind == "api"
            else "SELECT has_table_privilege('public.email_outbox', 'UPDATE') "
            "AND has_column_privilege('public.users', 'email', 'SELECT')"
        )
        if not connection.exec_driver_sql(required).scalar_one():
            raise DatabasePermissionError(
                "Runtime role is missing the permissions needed by this process."
            )
        expected = (
            {
                "users": "SELECT,INSERT,UPDATE",
                "user_sessions": "SELECT,INSERT,DELETE",
                "email_verification_tokens": "SELECT,INSERT,UPDATE,DELETE",
                "password_reset_tokens": "SELECT,INSERT,UPDATE,DELETE",
                "email_outbox": "INSERT",
            }
            if kind == "api"
            else {
                "user_sessions": "SELECT,DELETE",
                "email_verification_tokens": "SELECT,DELETE",
                "password_reset_tokens": "SELECT,DELETE",
                "email_outbox": "SELECT,UPDATE,DELETE",
            }
        )
        for table, privileges in expected.items():
            for privilege in privileges.split(","):
                if not connection.exec_driver_sql(
                    "SELECT has_table_privilege(%s, %s)", ("public." + table, privilege)
                ).scalar_one():
                    raise DatabasePermissionError("Runtime role is missing required table grants.")
        for table in APP_TABLES:
            if connection.exec_driver_sql(
                "SELECT has_table_privilege(%s, 'TRUNCATE,TRIGGER,REFERENCES')",
                ("public." + table,),
            ).scalar_one():
                raise DatabasePermissionError(
                    "Runtime roles must not have extra table-management grants."
                )
        required_columns = (
            (("email_outbox", "SELECT", ("id", "created_at")),)
            if kind == "api"
            else (
                ("users", "SELECT", ("id", "email", "email_verified_at")),
                ("user_sessions", "UPDATE", ("created_at",)),
                ("email_verification_tokens", "UPDATE", ("created_at",)),
                ("password_reset_tokens", "UPDATE", ("created_at",)),
            )
        )
        for table, privilege, columns in required_columns:
            for column in columns:
                if not connection.exec_driver_sql(
                    "SELECT has_column_privilege(%s, %s, %s)",
                    ("public." + table, column, privilege),
                ).scalar_one():
                    raise DatabasePermissionError("Runtime role is missing required column grants.")
        restricted_columns = (
            (
                ("email_outbox", "SELECT", ("id", "created_at")),
                ("email_outbox", "UPDATE", ()),
                ("user_sessions", "UPDATE", ()),
            )
            if kind == "api"
            else (
                ("users", "SELECT", ("id", "email", "email_verified_at")),
                ("user_sessions", "UPDATE", ("created_at",)),
                ("email_verification_tokens", "UPDATE", ("created_at",)),
                ("password_reset_tokens", "UPDATE", ("created_at",)),
            )
        )
        for table, privilege, allowed in restricted_columns:
            columns = (
                connection.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                )
                .scalars()
                .all()
            )
            for column in columns:
                if (
                    column not in allowed
                    and connection.exec_driver_sql(
                        "SELECT has_column_privilege(%s, %s, %s)",
                        ("public." + table, column, privilege),
                    ).scalar_one()
                ):
                    raise DatabasePermissionError("Runtime role has excessive column privileges.")
        if (
            kind == "api"
            and connection.exec_driver_sql(
                "SELECT has_table_privilege('public.email_outbox', 'UPDATE,DELETE')"
            ).scalar_one()
        ):
            raise DatabasePermissionError("The API must not modify existing delivery jobs.")
        if (
            kind == "worker"
            and connection.exec_driver_sql(
                "SELECT has_any_column_privilege('public.email_outbox', 'INSERT')"
            ).scalar_one()
        ):
            raise DatabasePermissionError("The delivery worker must not enqueue arbitrary jobs.")
