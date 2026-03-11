"""Run Alembic migrations with a PostgreSQL advisory lock."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse

import psycopg

DEFAULT_LOCK_TIMEOUT_SECONDS = 300
LOCK_POLL_INTERVAL_SECONDS = 1


def log(message: str) -> None:
    """Print a migration log line with flush for real-time visibility."""
    print(message, flush=True)


def normalize_postgres_url(database_url: str) -> str:
    """Convert SQLAlchemy-style PostgreSQL URLs into libpq-compatible URLs."""
    if database_url.startswith("postgresql+") and "://" in database_url:
        return f"postgresql://{database_url.split('://', maxsplit=1)[1]}"

    return database_url


def parse_lock_timeout_seconds() -> int:
    """Read lock wait timeout from env with sane defaults."""
    raw_value = os.getenv("MIGRATION_LOCK_TIMEOUT_SECONDS")
    if raw_value is None or raw_value == "":
        return DEFAULT_LOCK_TIMEOUT_SECONDS

    try:
        timeout = int(raw_value)
    except ValueError:
        log(
            "migrate: invalid MIGRATION_LOCK_TIMEOUT_SECONDS value; "
            f"using default {DEFAULT_LOCK_TIMEOUT_SECONDS}s"
        )

        return DEFAULT_LOCK_TIMEOUT_SECONDS

    if timeout <= 0:
        log(
            "migrate: non-positive MIGRATION_LOCK_TIMEOUT_SECONDS value; "
            f"using default {DEFAULT_LOCK_TIMEOUT_SECONDS}s"
        )

        return DEFAULT_LOCK_TIMEOUT_SECONDS

    return timeout


def derive_lock_key(database_url: str) -> int:
    """Return a stable lock key from DB name unless overridden by env."""
    override = os.getenv("MIGRATION_LOCK_KEY")
    if override:
        try:
            return int(override)
        except ValueError:
            log(
                "migrate: invalid MIGRATION_LOCK_KEY value; "
                "deriving key from database name"
            )

    parsed = urlparse(database_url)
    database_name = unquote(parsed.path.lstrip("/")) or "default"
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    lock_scope = f"{host}:{port}/{database_name}"
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    lock_key = int.from_bytes(digest, byteorder="big", signed=True)
    return lock_key or 1


def try_acquire_lock(
    connection: psycopg.Connection,
    lock_key: int,
    timeout_seconds: int,
) -> bool:
    """Attempt to obtain a session-level advisory lock within timeout."""
    deadline = time.monotonic() + timeout_seconds
    logged_wait = False

    while True:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            acquired = bool(cursor.fetchone()[0])

        if acquired:
            return True

        if time.monotonic() >= deadline:
            return False

        if not logged_wait:
            log("migrate: lock busy, waiting for existing migration runner")
            logged_wait = True

        time.sleep(LOCK_POLL_INTERVAL_SECONDS)


def release_lock(connection: psycopg.Connection, lock_key: int) -> None:
    """Release advisory lock and emit a clear log line."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        unlocked = bool(cursor.fetchone()[0])

    if unlocked:
        log("migrate: lock released")
    else:
        log("migrate: lock was already released")


def run() -> int:
    """Execute migration workflow under an advisory lock."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log("migrate: DATABASE_URL is required")

        return 1

    normalized_database_url = normalize_postgres_url(database_url)
    lock_key = derive_lock_key(normalized_database_url)
    lock_timeout_seconds = parse_lock_timeout_seconds()

    log("migrate: acquiring advisory lock")
    log(f"migrate: lock key={lock_key} timeout={lock_timeout_seconds}s")

    try:
        with psycopg.connect(normalized_database_url, autocommit=True) as connection:
            if not try_acquire_lock(connection, lock_key, lock_timeout_seconds):
                log("migrate: failed to acquire lock before timeout")

                return 1

            log("migrate: lock acquired")
            try:
                log("migrate: running alembic upgrade head")
                result = subprocess.run(
                    ["uv", "run", "alembic", "upgrade", "head"], check=False
                )
            finally:
                release_lock(connection, lock_key)

            if result.returncode == 0:
                log("migrate: migrations succeeded")
            else:
                log("migrate: migrations failed")

            return result.returncode
    except Exception as exc:
        log(f"migrate: unexpected error: {exc}")

        return 1


if __name__ == "__main__":
    sys.exit(run())
