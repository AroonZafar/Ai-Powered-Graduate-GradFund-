"""Plain domain types shared by the repository layer and the eligibility engine.

No Flask, no database access: these are just validated facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional


@dataclass(frozen=True)
class StudentFacts:
    funding_mode: str  # 'funded_only' | 'open_to_unfunded'
    gpa_4: float  # linear conversion to a 4.0 scale (approximate)
    english_test: Optional[str]
    english_score: Optional[float]
    gre_total: Optional[int]
    annual_budget_usd: Optional[int]

    @classmethod
    def from_profile_row(cls, row: Mapping) -> "StudentFacts":
        return cls(
            funding_mode=row["funding_mode"],
            gpa_4=round(row["gpa"] / row["gpa_scale"] * 4.0, 2),
            english_test=row["english_test"],
            english_score=row["english_score"],
            gre_total=row["gre_total"],
            annual_budget_usd=row["annual_budget_usd"],
        )


@dataclass(frozen=True)
class FundingFact:
    kind: str  # RA | TA | GA | tuition_waiver | scholarship
    master_eligible: str  # yes | no | unknown
    intl_eligible: str  # yes | no | unknown
    description: str


@dataclass(frozen=True)
class DeadlineFact:
    intake: str  # fall | spring
    deadline_date: date
    funding_priority_date: Optional[date]


@dataclass(frozen=True)
class SourceFact:
    url: str
    verified_on: date


@dataclass(frozen=True)
class ProgramFacts:
    id: str
    university_name: str
    university_state: Optional[str]
    university_website: str
    degree_name: str
    field: str
    program_type: str
    duration_months: int
    tuition_intl_usd_per_year: Optional[int]
    living_cost_usd_per_year: Optional[int]
    cost_year: Optional[int]
    gre_policy: str
    min_gpa: Optional[float]
    ielts_min: Optional[float]
    toefl_min: Optional[int]
    english_exemption_notes: Optional[str]
    intl_admission: str
    intl_restrictions: Optional[str]
    contact_faculty_policy: str
    ms_assistantships: str
    ms_assistantship_notes: Optional[str]
    application_url: str
    verified_on: date
    deadlines: tuple[DeadlineFact, ...] = ()
    funding: tuple[FundingFact, ...] = ()
    sources: Mapping[str, SourceFact] = field(default_factory=dict)
