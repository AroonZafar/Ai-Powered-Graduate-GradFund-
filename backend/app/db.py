"""Database access and versioned migrations (SQLite for dev/test).

Migrations are plain .sql files applied in filename order. Each runs inside one
transaction together with its bookkeeping row, so a failing migration leaves no
partial schema. Applied migrations are checksummed; editing one after the fact is
an error (write a new migration instead).
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class MigrationError(RuntimeError):
    pass


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: we manage transactions explicitly via transaction().
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _migration_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.sql"))


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _ensure_bookkeeping(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, checksum TEXT NOT NULL, "
        "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')))"
    )


def pending_migrations(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    _ensure_bookkeeping(conn)
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    return [f.stem for f in _migration_files(directory) if f.stem not in applied]


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply all pending migrations. Returns the versions applied."""
    _ensure_bookkeeping(conn)
    applied = {r["version"]: r["checksum"] for r in conn.execute("SELECT version, checksum FROM schema_migrations")}
    done: list[str] = []
    for path in _migration_files(directory):
        version = path.stem
        sql = path.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        if version in applied:
            if applied[version] != checksum:
                raise MigrationError(f"Migration {version} was modified after being applied")
            continue
        # version/checksum are derived from file name and hash, never user input.
        script = (
            "BEGIN;\n"
            f"{sql}\n"
            f"INSERT INTO schema_migrations (version, checksum) VALUES ('{version}', '{checksum}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise MigrationError(f"Migration {version} failed: {exc}") from exc
        done.append(version)
    return done


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.extensions["gradfund_config"].database_path)
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
