"""Program-fit engine: decides whether a program is worth a student's time.

Pure functions over plain facts (no I/O, no clock access: `today` is passed in), so every rule
is unit-testable. The engine only reports what the stored, sourced program data supports; it
never states that funding is guaranteed.

Severity:
  blocker - applying is unlikely to work for this student as things stand
  warning - a real risk or a missing/unverified fact the student should resolve first
  info    - useful context
Verdict: poor_fit if any blocker, fit_with_caveats if any warning, else good_fit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..domain import ProgramFacts, StudentFacts

BLOCKER, WARNING, INFO = "blocker", "warning", "info"
GOOD_FIT, FIT_WITH_CAVEATS, POOR_FIT = "good_fit", "fit_with_caveats", "poor_fit"
VERDICT_ORDER = {GOOD_FIT: 0, FIT_WITH_CAVEATS: 1, POOR_FIT: 2}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class FitResult:
    verdict: str
    findings: tuple[Finding, ...]
    annual_cost_before_funding_usd: Optional[int]
    total_cost_before_funding_usd: Optional[int]
    next_deadline: Optional[date]

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == WARNING)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "findings": [{"code": f.code, "severity": f.severity, "message": f.message} for f in self.findings],
            "estimated_annual_cost_before_funding_usd": self.annual_cost_before_funding_usd,
            "estimated_total_cost_before_funding_usd": self.total_cost_before_funding_usd,
            "next_deadline": self.next_deadline.isoformat() if self.next_deadline else None,
        }


def _confirmed_funding(program: ProgramFacts):
    return [f for f in program.funding if f.master_eligible == "yes" and f.intl_eligible == "yes"]


def _possible_funding(program: ProgramFacts):
    return [
        f for f in program.funding
        if f.master_eligible in ("yes", "unknown") and f.intl_eligible in ("yes", "unknown")
        and not (f.master_eligible == "yes" and f.intl_eligible == "yes")
    ]


def _admission_rules(student: StudentFacts, program: ProgramFacts) -> list[Finding]:
    out: list[Finding] = []
    if program.intl_admission == "closed":
        out.append(Finding("INTL_NOT_ACCEPTED", BLOCKER,
                           "This program does not accept international students."))
    elif program.intl_admission == "unknown":
        out.append(Finding("INTL_ELIGIBILITY_UNVERIFIED", WARNING,
                           "We could not verify whether this program accepts international students."))
    if program.min_gpa is not None and student.gpa_4 < program.min_gpa:
        out.append(Finding("GPA_BELOW_MINIMUM", BLOCKER,
                           f"Your GPA converts to about {student.gpa_4:.2f}/4.0 (approximate), below the "
                           f"program minimum of {program.min_gpa:.2f}."))
    if program.gre_policy == "required" and student.gre_total is None:
        out.append(Finding("GRE_REQUIRED_MISSING", WARNING, "The program requires GRE scores and your profile has none."))
    out.extend(_english_rules(student, program))
    return out


def _english_rules(student: StudentFacts, program: ProgramFacts) -> list[Finding]:
    if program.ielts_min is None and program.toefl_min is None:
        return []
    note = f" Exemptions: {program.english_exemption_notes}" if program.english_exemption_notes else ""
    if student.english_test is None:
        return [Finding("ENGLISH_TEST_MISSING", WARNING,
                        "The program lists an English proficiency minimum and your profile has no test score." + note)]
    if student.english_test == "ielts" and program.ielts_min is not None:
        if student.english_score < program.ielts_min:
            return [Finding("ENGLISH_BELOW_MINIMUM", WARNING,
                            f"Your IELTS {student.english_score:g} is below the program minimum of "
                            f"{program.ielts_min:g}; a retake would be needed before applying.")]
        return []
    if student.english_test == "toefl_ibt" and program.toefl_min is not None:
        if student.english_score < program.toefl_min:
            return [Finding("ENGLISH_BELOW_MINIMUM", WARNING,
                            f"Your TOEFL iBT {student.english_score:g} is below the program minimum of "
                            f"{program.toefl_min}; a retake would be needed before applying.")]
        return []
    return [Finding("ENGLISH_TEST_UNCHECKED", WARNING,
                    "Your English test type cannot be compared with this program's listed minimums; "
                    "confirm with the program that it is accepted.")]


def _funding_rules(student: StudentFacts, program: ProgramFacts) -> list[Finding]:
    out: list[Finding] = []
    confirmed, possible = _confirmed_funding(program), _possible_funding(program)
    kinds = ", ".join(sorted({f.kind for f in confirmed}))
    if confirmed:
        out.append(Finding("FUNDING_CONFIRMED", INFO,
                           f"Published sources list funding open to international master's students ({kinds}). "
                           "This is evidence of availability, not a guarantee of an award."))
    elif possible or program.ms_assistantships in ("professor_hires", "department_assigns", "both"):
        out.append(Finding("FUNDING_UNVERIFIED", WARNING,
                           "Some funding is mentioned, but eligibility for international master's students "
                           "is not confirmed by the sources we have."))
    elif program.ms_assistantships == "unknown":
        out.append(Finding("FUNDING_UNKNOWN", WARNING,
                           "We have no verified information about master's funding for this program."))
    elif student.funding_mode == "funded_only":
        out.append(Finding("NO_MASTERS_FUNDING", BLOCKER,
                           "The program lists no master's assistantships or funding, and you need funding."))
    else:
        out.append(Finding("NO_MASTERS_FUNDING", INFO,
                           "The program lists no master's funding, so plan for the full cost."))

    if program.ms_assistantships == "department_assigns":
        out.append(Finding("DEPARTMENT_ASSIGNS_ASSISTANTSHIPS", WARNING,
                           "Assistantships are assigned by the department, so emailing professors is "
                           "unlikely to secure one."))
    if program.program_type == "non_thesis":
        out.append(Finding("NON_THESIS_PROGRAM", WARNING,
                           "This is a non-thesis program; professor-led research assistantships are unlikely."))
    if program.contact_faculty_policy in ("discouraged", "prohibited"):
        verb = "asks applicants not to" if program.contact_faculty_policy == "discouraged" else "prohibits applicants from"
        out.append(Finding("CONTACT_FACULTY_RESTRICTED", WARNING,
                           f"The department {verb} email faculty before applying."))
    return out


def _cost(program: ProgramFacts) -> tuple[Optional[int], Optional[int]]:
    if program.tuition_intl_usd_per_year is None or program.living_cost_usd_per_year is None:
        return None, None
    annual = program.tuition_intl_usd_per_year + program.living_cost_usd_per_year
    return annual, round(annual * program.duration_months / 12)


def _cost_rules(student: StudentFacts, program: ProgramFacts, annual: Optional[int]) -> list[Finding]:
    if student.funding_mode != "open_to_unfunded":
        return []
    if annual is None:
        return [Finding("COST_INCOMPLETE", WARNING, "Tuition or living-cost data is missing, so total cost cannot be estimated.")]
    if student.annual_budget_usd is not None and annual > student.annual_budget_usd:
        has_confirmed = bool(_confirmed_funding(program))
        msg = (f"Estimated annual cost before funding (${annual:,}) exceeds your budget "
               f"(${student.annual_budget_usd:,}).")
        if has_confirmed:
            return [Finding("COST_EXCEEDS_BUDGET", INFO, msg + " Funding may reduce this; award amounts are not published.")]
        return [Finding("COST_EXCEEDS_BUDGET", WARNING, msg)]
    return []


def _deadline_rules(program: ProgramFacts, today: date) -> tuple[list[Finding], Optional[date]]:
    if not program.deadlines:
        return [Finding("DEADLINE_UNKNOWN", WARNING, "No application deadline is on record for this program.")], None
    upcoming = sorted(d.deadline_date for d in program.deadlines if d.deadline_date >= today)
    if not upcoming:
        return [Finding("DEADLINES_PASSED", WARNING, "All recorded application deadlines have passed.")], None
    return [], upcoming[0]


def _staleness_rules(program: ProgramFacts, today: date, stale_after_days: int) -> list[Finding]:
    age = (today - program.verified_on).days
    if age > stale_after_days:
        return [Finding("DATA_STALE", WARNING,
                        f"This program's data was last verified {age} days ago; check the official page.")]
    return []


def evaluate(student: StudentFacts, program: ProgramFacts, today: date, stale_after_days: int = 120) -> FitResult:
    annual, total = _cost(program)
    deadline_findings, next_deadline = _deadline_rules(program, today)
    findings = [
        *_admission_rules(student, program),
        *_funding_rules(student, program),
        *_cost_rules(student, program, annual),
        *deadline_findings,
        *_staleness_rules(program, today, stale_after_days),
    ]
    if any(f.severity == BLOCKER for f in findings):
        verdict = POOR_FIT
    elif any(f.severity == WARNING for f in findings):
        verdict = FIT_WITH_CAVEATS
    else:
        verdict = GOOD_FIT
    return FitResult(verdict, tuple(findings), annual, total, next_deadline)
