"""Persistence for programs: import (always as draft), review/publish, and reads."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from ..db import transaction
from ..domain import DeadlineFact, FundingFact, ProgramFacts, SourceFact
from .schemas import ProgramImport, required_source_keys

_PROGRAM_COLUMNS = (
    "degree_name", "field", "program_type", "duration_months", "tuition_intl_usd_per_year",
    "living_cost_usd_per_year", "cost_year", "gre_policy", "min_gpa", "ielts_min", "toefl_min",
    "english_exemption_notes", "intl_admission", "intl_restrictions", "contact_faculty_policy",
    "ms_assistantships", "ms_assistantship_notes",
)


class ProgramNotFound(Exception):
    pass


class PublishBlocked(Exception):
    """Raised when a program fails the provenance checks required for publishing."""


def _content_hash(data: ProgramImport) -> str:
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def import_program(conn: sqlite3.Connection, data: ProgramImport) -> tuple[str, str]:
    """Insert or update a program as a draft. Returns (program_id, outcome).

    outcome: 'created' | 'updated' | 'unchanged'. Changed content is always sent back to
    draft so it must be re-reviewed; identical content leaves the review state untouched.
    """
    new_hash = _content_hash(data)
    verified_on = data.oldest_verified_on().isoformat()
    with transaction(conn):
        uni = conn.execute("SELECT id FROM universities WHERE name = ?", (data.university_name,)).fetchone()
        if uni is None:
            university_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO universities (id, name, state, website) VALUES (?, ?, ?, ?)",
                (university_id, data.university_name, data.university_state, str(data.university_website)),
            )
        else:
            university_id = uni["id"]
            conn.execute("UPDATE universities SET state = ?, website = ? WHERE id = ?",
                         (data.university_state, str(data.university_website), university_id))

        existing = conn.execute(
            "SELECT id, content_hash FROM programs WHERE university_id = ? AND degree_name = ?",
            (university_id, data.degree_name),
        ).fetchone()
        values = [getattr(data, c) for c in _PROGRAM_COLUMNS]

        if existing is not None and existing["content_hash"] == new_hash:
            return existing["id"], "unchanged"

        if existing is None:
            program_id, outcome = str(uuid.uuid4()), "created"
            cols = ", ".join(_PROGRAM_COLUMNS)
            marks = ", ".join("?" for _ in _PROGRAM_COLUMNS)
            conn.execute(
                f"INSERT INTO programs (id, university_id, {cols}, application_url, status, content_hash, verified_on) "
                f"VALUES (?, ?, {marks}, ?, 'draft', ?, ?)",
                [program_id, university_id, *values, str(data.application_url), new_hash, verified_on],
            )
        else:
            program_id, outcome = existing["id"], "updated"
            sets = ", ".join(f"{c} = ?" for c in _PROGRAM_COLUMNS)
            conn.execute(
                f"UPDATE programs SET {sets}, application_url = ?, status = 'draft', reviewed_by = NULL, "
                "reviewed_at = NULL, content_hash = ?, verified_on = ?, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                [*values, str(data.application_url), new_hash, verified_on, program_id],
            )
            for table in ("program_deadlines", "funding_evidence", "field_sources"):
                conn.execute(f"DELETE FROM {table} WHERE program_id = ?", (program_id,))

        for d in data.deadlines:
            conn.execute(
                "INSERT INTO program_deadlines (program_id, intake, deadline_date, funding_priority_date) VALUES (?, ?, ?, ?)",
                (program_id, d.intake, d.deadline_date.isoformat(),
                 d.funding_priority_date.isoformat() if d.funding_priority_date else None),
            )
        for f in data.funding:
            conn.execute(
                "INSERT INTO funding_evidence (program_id, kind, master_eligible, intl_eligible, description) VALUES (?, ?, ?, ?, ?)",
                (program_id, f.kind, f.master_eligible, f.intl_eligible, f.description),
            )
        for key, src in data.sources.items():
            conn.execute(
                "INSERT INTO field_sources (program_id, field_key, url, verified_on) VALUES (?, ?, ?, ?)",
                (program_id, key, str(src.url), src.verified_on.isoformat()),
            )
    return program_id, outcome


def publish_program(conn: sqlite3.Connection, program_id: str, reviewer: str) -> None:
    """Mark a draft as published after re-checking provenance against what is stored."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise PublishBlocked("A reviewer name is required")
    with transaction(conn):
        row = conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
        if row is None:
            raise ProgramNotFound(program_id)
        has_deadlines = conn.execute("SELECT 1 FROM program_deadlines WHERE program_id = ?", (program_id,)).fetchone() is not None
        has_funding = conn.execute("SELECT 1 FROM funding_evidence WHERE program_id = ?", (program_id,)).fetchone() is not None
        have = {r["field_key"] for r in conn.execute("SELECT field_key FROM field_sources WHERE program_id = ?", (program_id,))}
        required = required_source_keys(
            program_type=row["program_type"], duration_months=row["duration_months"],
            tuition=row["tuition_intl_usd_per_year"], living=row["living_cost_usd_per_year"],
            gre_policy=row["gre_policy"], min_gpa=row["min_gpa"], ielts_min=row["ielts_min"],
            toefl_min=row["toefl_min"], intl_admission=row["intl_admission"],
            contact_faculty_policy=row["contact_faculty_policy"], ms_assistantships=row["ms_assistantships"],
            has_deadlines=has_deadlines, has_funding=has_funding,
        )
        missing = sorted(required - have)
        if missing:
            raise PublishBlocked(f"Missing sources for: {', '.join(missing)}")
        conn.execute(
            "UPDATE programs SET status = 'published', reviewed_by = ?, reviewed_at = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
            (reviewer, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), program_id),
        )


def list_drafts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT p.id, u.name AS university_name, p.degree_name FROM programs p "
        "JOIN universities u ON u.id = p.university_id WHERE p.status = 'draft' ORDER BY u.name, p.degree_name"
    ).fetchall()


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[ProgramFacts]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    marks = ", ".join("?" for _ in ids)
    deadlines: dict[str, list[DeadlineFact]] = {i: [] for i in ids}
    for d in conn.execute(f"SELECT * FROM program_deadlines WHERE program_id IN ({marks})", ids):
        deadlines[d["program_id"]].append(DeadlineFact(
            d["intake"], date.fromisoformat(d["deadline_date"]),
            date.fromisoformat(d["funding_priority_date"]) if d["funding_priority_date"] else None))
    funding: dict[str, list[FundingFact]] = {i: [] for i in ids}
    for f in conn.execute(f"SELECT * FROM funding_evidence WHERE program_id IN ({marks}) ORDER BY id", ids):
        funding[f["program_id"]].append(FundingFact(f["kind"], f["master_eligible"], f["intl_eligible"], f["description"]))
    sources: dict[str, dict[str, SourceFact]] = {i: {} for i in ids}
    for s in conn.execute(f"SELECT * FROM field_sources WHERE program_id IN ({marks})", ids):
        sources[s["program_id"]][s["field_key"]] = SourceFact(s["url"], date.fromisoformat(s["verified_on"]))
    return [
        ProgramFacts(
            id=r["id"], university_name=r["university_name"], university_state=r["state"],
            university_website=r["website"], degree_name=r["degree_name"], field=r["field"],
            program_type=r["program_type"], duration_months=r["duration_months"],
            tuition_intl_usd_per_year=r["tuition_intl_usd_per_year"],
            living_cost_usd_per_year=r["living_cost_usd_per_year"], cost_year=r["cost_year"],
            gre_policy=r["gre_policy"], min_gpa=r["min_gpa"], ielts_min=r["ielts_min"],
            toefl_min=r["toefl_min"], english_exemption_notes=r["english_exemption_notes"],
            intl_admission=r["intl_admission"], intl_restrictions=r["intl_restrictions"],
            contact_faculty_policy=r["contact_faculty_policy"], ms_assistantships=r["ms_assistantships"],
            ms_assistantship_notes=r["ms_assistantship_notes"], application_url=r["application_url"],
            verified_on=date.fromisoformat(r["verified_on"]),
            deadlines=tuple(sorted(deadlines[r["id"]], key=lambda d: d.deadline_date)),
            funding=tuple(funding[r["id"]]), sources=sources[r["id"]],
        )
        for r in rows
    ]


_SELECT = (
    "SELECT p.*, u.name AS university_name, u.state, u.website FROM programs p "
    "JOIN universities u ON u.id = p.university_id WHERE p.status = 'published'"
)


def list_published(conn: sqlite3.Connection, *, field: Optional[str] = None,
                   program_type: Optional[str] = None, text: Optional[str] = None) -> list[ProgramFacts]:
    sql, params = _SELECT, []
    if field:
        sql += " AND p.field = ?"
        params.append(field)
    if program_type:
        sql += " AND p.program_type = ?"
        params.append(program_type)
    if text:
        like = f"%{_like_escape(text)}%"
        sql += " AND (u.name LIKE ? ESCAPE '\\' OR p.degree_name LIKE ? ESCAPE '\\')"
        params += [like, like]
    sql += " ORDER BY u.name COLLATE NOCASE, p.degree_name COLLATE NOCASE"
    return _build(conn, conn.execute(sql, params).fetchall())


def get_published(conn: sqlite3.Connection, program_id: str) -> Optional[ProgramFacts]:
    rows = conn.execute(_SELECT + " AND p.id = ?", (program_id,)).fetchall()
    built = _build(conn, rows)
    return built[0] if built else None
