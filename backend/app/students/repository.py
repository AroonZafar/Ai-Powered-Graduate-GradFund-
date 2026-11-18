from __future__ import annotations

import sqlite3
from typing import Optional

from ..db import transaction
from .schemas import ProfileIn

_COLUMNS = ("full_name", "funding_mode", "gpa", "gpa_scale", "undergraduate_field",
            "english_test", "english_score", "gre_total", "annual_budget_usd")


def get_profile(conn: sqlite3.Connection, user_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        f"SELECT {', '.join(_COLUMNS)}, updated_at FROM student_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()


def upsert_profile(conn: sqlite3.Connection, user_id: str, data: ProfileIn) -> None:
    values = [getattr(data, c) for c in _COLUMNS]
    placeholders = ", ".join("?" for _ in _COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS)
    with transaction(conn):
        conn.execute(
            f"INSERT INTO student_profiles (user_id, {', '.join(_COLUMNS)}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(user_id) DO UPDATE SET {updates}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
            [user_id, *values],
        )
