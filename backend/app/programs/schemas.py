"""Import schema for program records and the provenance rules that guard publishing.

Provenance rule: every fact whose value is known must have a source URL and a verified date.
Values of 'unknown' (or null) are not facts and need no source.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Ternary = Literal["yes", "no", "unknown"]


def required_source_keys(*, program_type: str, duration_months: Optional[int], tuition: Optional[int],
                         living: Optional[int], gre_policy: str, min_gpa: Optional[float],
                         ielts_min: Optional[float], toefl_min: Optional[int], intl_admission: str,
                         contact_faculty_policy: str, ms_assistantships: str,
                         has_deadlines: bool, has_funding: bool) -> set[str]:
    """Source keys that must exist for the known facts of a program record."""
    keys = {"program_type"}
    if duration_months is not None:
        keys.add("duration")
    if tuition is not None:
        keys.add("tuition")
    if living is not None:
        keys.add("living_cost")
    if gre_policy != "unknown":
        keys.add("gre_policy")
    if min_gpa is not None:
        keys.add("min_gpa")
    if ielts_min is not None or toefl_min is not None:
        keys.add("english")
    if intl_admission != "unknown":
        keys.add("intl_admission")
    if contact_faculty_policy != "unknown":
        keys.add("contact_faculty_policy")
    if ms_assistantships != "unknown":
        keys.add("assistantships")
    if has_deadlines:
        keys.add("deadlines")
    if has_funding:
        keys.add("funding")
    return keys


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceIn(_Strict):
    url: HttpUrl
    verified_on: date

    @field_validator("verified_on")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("verified_on cannot be in the future")
        return v


class DeadlineIn(_Strict):
    intake: Literal["fall", "spring"]
    deadline_date: date
    funding_priority_date: Optional[date] = None


class FundingIn(_Strict):
    kind: Literal["RA", "TA", "GA", "tuition_waiver", "scholarship"]
    master_eligible: Ternary
    intl_eligible: Ternary
    description: str = Field(min_length=1, max_length=500)


class ProgramImport(_Strict):
    university_name: str = Field(min_length=1, max_length=200)
    university_state: Optional[str] = Field(default=None, max_length=50)
    university_website: HttpUrl
    degree_name: str = Field(min_length=1, max_length=200)
    field: Literal["ai", "cybersecurity", "cs", "data_science", "other"]
    program_type: Literal["thesis", "thesis_optional", "non_thesis", "research_based"]
    duration_months: int = Field(ge=6, le=60)
    tuition_intl_usd_per_year: Optional[int] = Field(default=None, ge=0)
    living_cost_usd_per_year: Optional[int] = Field(default=None, ge=0)
    cost_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    gre_policy: Literal["required", "optional", "not_considered", "unknown"]
    min_gpa: Optional[float] = Field(default=None, ge=0, le=4)
    ielts_min: Optional[float] = Field(default=None, ge=0, le=9)
    toefl_min: Optional[int] = Field(default=None, ge=0, le=120)
    english_exemption_notes: Optional[str] = Field(default=None, max_length=1000)
    intl_admission: Literal["open", "closed", "unknown"]
    intl_restrictions: Optional[str] = Field(default=None, max_length=1000)
    contact_faculty_policy: Literal["encouraged", "allowed", "discouraged", "prohibited", "unknown"]
    ms_assistantships: Literal["professor_hires", "department_assigns", "both", "none_listed", "unknown"]
    ms_assistantship_notes: Optional[str] = Field(default=None, max_length=1000)
    application_url: HttpUrl
    deadlines: list[DeadlineIn] = Field(default_factory=list)
    funding: list[FundingIn] = Field(default_factory=list)
    sources: dict[str, SourceIn]

    @model_validator(mode="after")
    def _check_provenance_and_consistency(self) -> "ProgramImport":
        required = required_source_keys(
            program_type=self.program_type, duration_months=self.duration_months,
            tuition=self.tuition_intl_usd_per_year, living=self.living_cost_usd_per_year,
            gre_policy=self.gre_policy, min_gpa=self.min_gpa, ielts_min=self.ielts_min,
            toefl_min=self.toefl_min, intl_admission=self.intl_admission,
            contact_faculty_policy=self.contact_faculty_policy, ms_assistantships=self.ms_assistantships,
            has_deadlines=bool(self.deadlines), has_funding=bool(self.funding),
        )
        missing = sorted(required - set(self.sources))
        if missing:
            raise ValueError(f"Missing source (url + verified_on) for: {', '.join(missing)}")
        unknown_keys = sorted(set(self.sources) - required)
        if unknown_keys:
            raise ValueError(f"Sources given for facts that are not set: {', '.join(unknown_keys)}")
        if (self.tuition_intl_usd_per_year is not None or self.living_cost_usd_per_year is not None) and self.cost_year is None:
            raise ValueError("cost_year is required when tuition or living cost is given")
        intakes = [d.intake for d in self.deadlines]
        if len(intakes) != len(set(intakes)):
            raise ValueError("Duplicate intake in deadlines")
        if self.ms_assistantships == "none_listed" and any(f.kind in ("RA", "TA", "GA") for f in self.funding):
            raise ValueError("ms_assistantships is 'none_listed' but RA/TA/GA funding evidence was supplied")
        return self

    def oldest_verified_on(self) -> date:
        """Record-level verification date is the oldest source date (conservative)."""
        return min(s.verified_on for s in self.sources.values())
