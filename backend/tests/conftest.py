import copy
import secrets
from datetime import date

import pytest

from app import create_app
from app.config import Config
from app.db import connect, migrate

FIXED_TODAY = date(2026, 11, 18)


@pytest.fixture
def config(tmp_path):
    # Random per-run secret: nothing is hardcoded.
    return Config(env="test", secret_key=secrets.token_urlsafe(48), database_path=str(tmp_path / "test.db"))


@pytest.fixture
def conn(config):
    c = connect(config.database_path)
    migrate(c)
    yield c
    c.close()


@pytest.fixture
def app(config, conn):
    return create_app(config, today=lambda: FIXED_TODAY)


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email="student@example.org", password="correct-horse-battery"):
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.get_json()
    return {"Authorization": f"Bearer {resp.get_json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


PROFILE = {
    "full_name": "Test Student", "funding_mode": "funded_only", "gpa": 3.4, "gpa_scale": 4.0,
    "undergraduate_field": "Computer Science", "english_test": "ielts", "english_score": 7.0,
    "gre_total": 315, "annual_budget_usd": 10000,
}


def profile(**overrides):
    return {**copy.deepcopy(PROFILE), **overrides}


def program_payload(**overrides):
    """SYNTHETIC test fixture: a fictional university and example.edu URLs. Not product data."""
    src = {"url": "https://example.edu/source", "verified_on": "2026-10-01"}
    base = {
        "university_name": "Testville State University",
        "university_state": "TS",
        "university_website": "https://example.edu/",
        "degree_name": "MS in Artificial Intelligence",
        "field": "ai",
        "program_type": "thesis",
        "duration_months": 24,
        "tuition_intl_usd_per_year": 20000,
        "living_cost_usd_per_year": 15000,
        "cost_year": 2026,
        "gre_policy": "optional",
        "min_gpa": 3.0,
        "ielts_min": 6.5,
        "toefl_min": 80,
        "english_exemption_notes": None,
        "intl_admission": "open",
        "intl_restrictions": None,
        "contact_faculty_policy": "allowed",
        "ms_assistantships": "professor_hires",
        "ms_assistantship_notes": None,
        "application_url": "https://example.edu/apply",
        "deadlines": [{"intake": "fall", "deadline_date": "2027-01-15", "funding_priority_date": None}],
        "funding": [{"kind": "RA", "master_eligible": "yes", "intl_eligible": "yes", "description": "Fixture RA evidence"}],
        "sources": {k: dict(src) for k in (
            "program_type", "duration", "tuition", "living_cost", "gre_policy", "min_gpa", "english",
            "intl_admission", "contact_faculty_policy", "assistantships", "deadlines", "funding")},
    }
    base.update(overrides)
    return base
