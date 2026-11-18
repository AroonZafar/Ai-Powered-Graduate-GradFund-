"""Account business logic. Takes a DB connection; knows nothing about HTTP."""
from __future__ import annotations

import sqlite3
import uuid

from ..db import transaction
from ..security import DUMMY_HASH, hash_password, verify_password


class EmailTaken(Exception):
    pass


class BadCredentials(Exception):
    pass


def register_user(conn: sqlite3.Connection, email: str, password: str) -> str:
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (user_id, email, pw_hash),
            )
    except sqlite3.IntegrityError as exc:
        if "users.email" in str(exc):
            raise EmailTaken() from exc
        raise
    return user_id


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> str:
    row = conn.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if row is None:
        verify_password(password, DUMMY_HASH)  # equalise timing with the found-user path
        raise BadCredentials()
    if not verify_password(password, row["password_hash"]):
        raise BadCredentials()
    return row["id"]


def user_exists(conn: sqlite3.Connection, user_id: str) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None


def verify_user_password(conn: sqlite3.Connection, user_id: str, password: str) -> bool:
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None and verify_password(password, row["password_hash"])


def delete_user(conn: sqlite3.Connection, user_id: str) -> None:
    """Hard-delete the account; dependent rows are removed by ON DELETE CASCADE."""
    with transaction(conn):
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
