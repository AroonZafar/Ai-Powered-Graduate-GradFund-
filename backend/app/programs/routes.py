from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from flask import Blueprint, current_app, g, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from ..auth.guard import require_auth
from ..db import get_db
from ..domain import ProgramFacts, StudentFacts
from ..eligibility.engine import VERDICT_ORDER, FitResult, evaluate
from ..errors import ApiError
from ..students import repository as students_repo
from . import repository

bp = Blueprint("programs", __name__, url_prefix="/api/v1")


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: Optional[Literal["ai", "cybersecurity", "cs", "data_science", "other"]] = None
    program_type: Optional[Literal["thesis", "thesis_optional", "non_thesis", "research_based"]] = None
    verdict: Optional[Literal["good_fit", "fit_with_caveats", "poor_fit"]] = None
    q: Optional[str] = Field(default=None, min_length=1, max_length=100)
    sort: Optional[Literal["fit", "university", "deadline", "cost"]] = None
    page: int = Field(default=1, ge=1, le=10_000)
    per_page: int = Field(default=20, ge=1, le=50)


def _today() -> date:
    return current_app.extensions["today"]()


def _student_facts(user_id: str) -> Optional[StudentFacts]:
    row = students_repo.get_profile(get_db(), user_id)
    return StudentFacts.from_profile_row(row) if row is not None else None


def _program_json(p: ProgramFacts, fit: Optional[FitResult]) -> dict:
    return {
        "id": p.id,
        "university": {"name": p.university_name, "state": p.university_state, "website": p.university_website},
        "degree_name": p.degree_name,
        "field": p.field,
        "program_type": p.program_type,
        "duration_months": p.duration_months,
        "tuition_intl_usd_per_year": p.tuition_intl_usd_per_year,
        "living_cost_usd_per_year": p.living_cost_usd_per_year,
        "cost_year": p.cost_year,
        "gre_policy": p.gre_policy,
        "min_gpa": p.min_gpa,
        "ielts_min": p.ielts_min,
        "toefl_min": p.toefl_min,
        "english_exemption_notes": p.english_exemption_notes,
        "intl_admission": p.intl_admission,
        "intl_restrictions": p.intl_restrictions,
        "contact_faculty_policy": p.contact_faculty_policy,
        "ms_assistantships": p.ms_assistantships,
        "ms_assistantship_notes": p.ms_assistantship_notes,
        "application_url": p.application_url,
        "deadlines": [
            {"intake": d.intake, "deadline_date": d.deadline_date.isoformat(),
             "funding_priority_date": d.funding_priority_date.isoformat() if d.funding_priority_date else None}
            for d in p.deadlines
        ],
        "funding": [
            {"kind": f.kind, "master_eligible": f.master_eligible,
             "intl_eligible": f.intl_eligible, "description": f.description}
            for f in p.funding
        ],
        "sources": {k: {"url": s.url, "verified_on": s.verified_on.isoformat()} for k, s in p.sources.items()},
        "verified_on": p.verified_on.isoformat(),
        "fit": fit.to_dict() if fit else None,
    }


def _sort_key(sort: str, p: ProgramFacts, fit: Optional[FitResult]):
    name = (p.university_name.lower(), p.degree_name.lower())
    if sort == "fit":
        return (VERDICT_ORDER[fit.verdict], fit.warning_count, *name)
    if sort == "deadline":
        nd = fit.next_deadline if fit else None
        return (nd is None, nd or date.max, *name)
    if sort == "cost":
        annual = (p.tuition_intl_usd_per_year + p.living_cost_usd_per_year
                  if p.tuition_intl_usd_per_year is not None and p.living_cost_usd_per_year is not None else None)
        return (annual is None, annual or 0, *name)
    return name


@bp.get("/programs")
@require_auth
def list_programs():
    q = ListQuery.model_validate(request.args.to_dict())
    student = _student_facts(g.user_id)
    if student is None and (q.verdict or q.sort == "fit"):
        raise ApiError(409, "PROFILE_REQUIRED", "Complete your profile to filter or sort by fit")

    cfg = current_app.extensions["gradfund_config"]
    today = _today()
    programs = repository.list_published(get_db(), field=q.field, program_type=q.program_type, text=q.q)
    # Fit depends on the student's profile, so it is computed before filtering/paginating.
    # The curated catalogue is small by design (accuracy over breadth).
    pairs = [(p, evaluate(student, p, today, cfg.stale_data_days) if student else None) for p in programs]
    if q.verdict:
        pairs = [(p, f) for p, f in pairs if f.verdict == q.verdict]

    sort = q.sort or ("fit" if student else "university")
    pairs.sort(key=lambda pf: _sort_key(sort, *pf))

    total = len(pairs)
    start = (q.page - 1) * q.per_page
    page = pairs[start:start + q.per_page]
    return jsonify({
        "data": [_program_json(p, f) for p, f in page],
        "meta": {"page": q.page, "per_page": q.per_page, "total": total,
                 "sort": sort, "profile_complete": student is not None},
    })


@bp.get("/programs/<program_id>")
@require_auth
def get_program(program_id: str):
    program = repository.get_published(get_db(), program_id)
    if program is None:
        raise ApiError(404, "PROGRAM_NOT_FOUND", "Program not found")
    student = _student_facts(g.user_id)
    cfg = current_app.extensions["gradfund_config"]
    fit = evaluate(student, program, _today(), cfg.stale_data_days) if student else None
    return jsonify(_program_json(program, fit))
