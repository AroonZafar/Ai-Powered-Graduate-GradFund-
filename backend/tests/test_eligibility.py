from dataclasses import replace
from datetime import date

import pytest

from app.domain import DeadlineFact, FundingFact, ProgramFacts, StudentFacts
from app.eligibility.engine import BLOCKER, FIT_WITH_CAVEATS, GOOD_FIT, INFO, POOR_FIT, WARNING, evaluate

TODAY = date(2026, 11, 18)

STUDENT = StudentFacts("funded_only", 3.4, "ielts", 7.0, 315, 10000)

# SYNTHETIC fixture program: fictional university, no real-world data.
PROGRAM = ProgramFacts(
    id="p1", university_name="Testville State University", university_state="TS",
    university_website="https://example.edu/", degree_name="MS in AI", field="ai", program_type="thesis",
    duration_months=24, tuition_intl_usd_per_year=20000, living_cost_usd_per_year=15000, cost_year=2026,
    gre_policy="optional", min_gpa=3.0, ielts_min=6.5, toefl_min=80, english_exemption_notes=None,
    intl_admission="open", intl_restrictions=None, contact_faculty_policy="allowed",
    ms_assistantships="professor_hires", ms_assistantship_notes=None, application_url="https://example.edu/apply",
    verified_on=date(2026, 10, 1),
    deadlines=(DeadlineFact("fall", date(2027, 1, 15), None),),
    funding=(FundingFact("RA", "yes", "yes", "fixture"),),
)


def codes(result, severity=None):
    return {f.code for f in result.findings if severity is None or f.severity == severity}


def test_strong_program_is_good_fit_with_costs_and_deadline():
    r = evaluate(STUDENT, PROGRAM, TODAY)
    assert r.verdict == GOOD_FIT
    assert codes(r, BLOCKER) == set() and codes(r, WARNING) == set()
    assert "FUNDING_CONFIRMED" in codes(r, INFO)
    assert r.annual_cost_before_funding_usd == 35000
    assert r.total_cost_before_funding_usd == 70000
    assert r.next_deadline == date(2027, 1, 15)


def test_funding_message_never_promises_an_award():
    msg = next(f.message for f in evaluate(STUDENT, PROGRAM, TODAY).findings if f.code == "FUNDING_CONFIRMED")
    assert "not a guarantee" in msg


def test_non_thesis_program_with_no_master_funding_blocks_a_funded_only_student():
    """The scenario from the product spec: great professor, but the program cannot fund a master's student."""
    prog = replace(PROGRAM, program_type="non_thesis", ms_assistantships="none_listed", funding=())
    r = evaluate(STUDENT, prog, TODAY)
    assert r.verdict == POOR_FIT
    assert "NO_MASTERS_FUNDING" in codes(r, BLOCKER)
    assert "NON_THESIS_PROGRAM" in codes(r, WARNING)


def test_same_unfunded_program_is_only_informational_for_open_to_unfunded_student():
    prog = replace(PROGRAM, ms_assistantships="none_listed", funding=())
    student = replace(STUDENT, funding_mode="open_to_unfunded", annual_budget_usd=50000)
    r = evaluate(student, prog, TODAY)
    assert r.verdict == GOOD_FIT
    assert "NO_MASTERS_FUNDING" in codes(r, INFO)


def test_unknown_funding_is_a_warning_not_a_blocker():
    prog = replace(PROGRAM, ms_assistantships="unknown", funding=())
    r = evaluate(STUDENT, prog, TODAY)
    assert r.verdict == FIT_WITH_CAVEATS
    assert "FUNDING_UNKNOWN" in codes(r, WARNING)


def test_funding_not_confirmed_for_international_masters_is_unverified():
    prog = replace(PROGRAM, funding=(FundingFact("RA", "unknown", "yes", "x"),))
    assert "FUNDING_UNVERIFIED" in codes(evaluate(STUDENT, prog, TODAY), WARNING)


def test_funding_explicitly_closed_to_masters_students_is_not_counted():
    prog = replace(PROGRAM, ms_assistantships="none_listed", funding=(FundingFact("RA", "no", "yes", "PhD only"),))
    assert "NO_MASTERS_FUNDING" in codes(evaluate(STUDENT, prog, TODAY), BLOCKER)


def test_department_assigned_assistantships_warn_against_cold_emailing():
    prog = replace(PROGRAM, ms_assistantships="department_assigns")
    assert "DEPARTMENT_ASSIGNS_ASSISTANTSHIPS" in codes(evaluate(STUDENT, prog, TODAY), WARNING)


@pytest.mark.parametrize("policy", ["discouraged", "prohibited"])
def test_faculty_contact_restrictions_warn(policy):
    prog = replace(PROGRAM, contact_faculty_policy=policy)
    assert "CONTACT_FACULTY_RESTRICTED" in codes(evaluate(STUDENT, prog, TODAY), WARNING)


def test_international_students_not_accepted_is_blocker():
    assert "INTL_NOT_ACCEPTED" in codes(evaluate(STUDENT, replace(PROGRAM, intl_admission="closed"), TODAY), BLOCKER)


def test_unknown_international_eligibility_is_warning():
    assert "INTL_ELIGIBILITY_UNVERIFIED" in codes(evaluate(STUDENT, replace(PROGRAM, intl_admission="unknown"), TODAY), WARNING)


def test_gpa_below_minimum_blocks_and_boundary_passes():
    assert "GPA_BELOW_MINIMUM" in codes(evaluate(replace(STUDENT, gpa_4=2.99), PROGRAM, TODAY), BLOCKER)
    assert "GPA_BELOW_MINIMUM" not in codes(evaluate(replace(STUDENT, gpa_4=3.0), PROGRAM, TODAY))


def test_gre_required_but_missing_warns_and_optional_does_not():
    required = replace(PROGRAM, gre_policy="required")
    assert "GRE_REQUIRED_MISSING" in codes(evaluate(replace(STUDENT, gre_total=None), required, TODAY), WARNING)
    assert "GRE_REQUIRED_MISSING" not in codes(evaluate(replace(STUDENT, gre_total=None), PROGRAM, TODAY))


def test_english_checks():
    assert "ENGLISH_BELOW_MINIMUM" in codes(evaluate(replace(STUDENT, english_score=6.0), PROGRAM, TODAY), WARNING)
    assert "ENGLISH_BELOW_MINIMUM" in codes(evaluate(replace(STUDENT, english_test="toefl_ibt", english_score=70), PROGRAM, TODAY), WARNING)
    assert "ENGLISH_TEST_MISSING" in codes(evaluate(replace(STUDENT, english_test=None, english_score=None), PROGRAM, TODAY), WARNING)
    assert "ENGLISH_TEST_UNCHECKED" in codes(evaluate(replace(STUDENT, english_test="duolingo", english_score=120), PROGRAM, TODAY), WARNING)
    no_requirement = replace(PROGRAM, ielts_min=None, toefl_min=None)
    assert not codes(evaluate(replace(STUDENT, english_test=None, english_score=None), no_requirement, TODAY), WARNING)


def test_cost_exceeding_budget_for_open_to_unfunded_student():
    student = replace(STUDENT, funding_mode="open_to_unfunded", annual_budget_usd=20000)
    unfunded = replace(PROGRAM, ms_assistantships="none_listed", funding=())
    assert "COST_EXCEEDS_BUDGET" in codes(evaluate(student, unfunded, TODAY), WARNING)
    # With confirmed funding it is downgraded to information because awards may reduce the cost.
    assert "COST_EXCEEDS_BUDGET" in codes(evaluate(student, PROGRAM, TODAY), INFO)


def test_incomplete_cost_data_flagged_for_unfunded_students_only():
    prog = replace(PROGRAM, tuition_intl_usd_per_year=None)
    unfunded_student = replace(STUDENT, funding_mode="open_to_unfunded")
    assert "COST_INCOMPLETE" in codes(evaluate(unfunded_student, prog, TODAY), WARNING)
    assert "COST_INCOMPLETE" not in codes(evaluate(STUDENT, prog, TODAY))
    assert evaluate(STUDENT, prog, TODAY).annual_cost_before_funding_usd is None


def test_deadline_rules():
    passed = replace(PROGRAM, deadlines=(DeadlineFact("fall", date(2026, 11, 17), None),))
    assert "DEADLINES_PASSED" in codes(evaluate(STUDENT, passed, TODAY), WARNING)
    on_day = replace(PROGRAM, deadlines=(DeadlineFact("fall", TODAY, None),))
    assert evaluate(STUDENT, on_day, TODAY).next_deadline == TODAY
    assert "DEADLINE_UNKNOWN" in codes(evaluate(STUDENT, replace(PROGRAM, deadlines=()), TODAY), WARNING)
    both = replace(PROGRAM, deadlines=(DeadlineFact("fall", date(2027, 1, 15), None), DeadlineFact("spring", date(2026, 12, 1), None)))
    assert evaluate(STUDENT, both, TODAY).next_deadline == date(2026, 12, 1)


def test_stale_data_flagged_after_threshold():
    old = replace(PROGRAM, verified_on=date(2026, 5, 1))
    assert "DATA_STALE" in codes(evaluate(STUDENT, old, TODAY, stale_after_days=120), WARNING)
    assert "DATA_STALE" not in codes(evaluate(STUDENT, old, TODAY, stale_after_days=365))


def test_student_gpa_conversion_from_profile_row():
    row = {"funding_mode": "funded_only", "gpa": 3.0, "gpa_scale": 5.0, "english_test": None,
           "english_score": None, "gre_total": None, "annual_budget_usd": None}
    assert StudentFacts.from_profile_row(row).gpa_4 == 2.4
