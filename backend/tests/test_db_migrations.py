import sqlite3

import pytest

from app.db import MigrationError, connect, migrate, pending_migrations, transaction


def test_applies_all_and_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "a.db"))
    first = migrate(conn)
    assert first == ["0001_users_profiles", "0002_programs"]
    assert migrate(conn) == []
    assert pending_migrations(conn) == []


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO student_profiles (user_id, full_name, funding_mode, gpa, gpa_scale, undergraduate_field)"
                     " VALUES ('nope', 'x', 'funded_only', 3, 4, 'cs')")


def test_modified_migration_is_detected(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "0001_a.sql").write_text("CREATE TABLE t (id INTEGER);")
    conn = connect(str(tmp_path / "b.db"))
    migrate(conn, d)
    (d / "0001_a.sql").write_text("CREATE TABLE t (id INTEGER, extra TEXT);")
    with pytest.raises(MigrationError, match="modified"):
        migrate(conn, d)


def test_failing_migration_rolls_back_completely(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "0001_bad.sql").write_text("CREATE TABLE ok_table (id INTEGER); CREATE TABLE ok_table (id INTEGER);")
    conn = connect(str(tmp_path / "c.db"))
    with pytest.raises(MigrationError):
        migrate(conn, d)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ok_table" not in tables
    assert conn.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()["n"] == 0


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO universities (id, name, website) VALUES ('1', 'U', 'https://e.edu')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT count(*) AS n FROM universities").fetchone()["n"] == 0


def test_db_rejects_publishing_without_reviewer(conn):
    conn.execute("INSERT INTO universities (id, name, website) VALUES ('u', 'U', 'https://e.edu')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO programs (id, university_id, degree_name, field, program_type, duration_months, gre_policy,"
            " intl_admission, contact_faculty_policy, ms_assistantships, application_url, status, content_hash, verified_on)"
            " VALUES ('p','u','MS','ai','thesis',24,'optional','open','allowed','unknown','https://e.edu','published','h','2026-01-01')")
