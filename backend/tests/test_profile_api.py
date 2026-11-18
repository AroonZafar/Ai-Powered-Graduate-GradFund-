import pytest

from conftest import profile, register


def test_create_read_update_profile(client, auth):
    put = client.put("/api/v1/profile", json=profile(), headers=auth)
    assert put.status_code == 200 and put.get_json()["full_name"] == "Test Student"
    changed = client.put("/api/v1/profile", json=profile(funding_mode="open_to_unfunded", annual_budget_usd=30000), headers=auth)
    assert changed.get_json()["funding_mode"] == "open_to_unfunded"
    assert client.get("/api/v1/profile", headers=auth).get_json()["annual_budget_usd"] == 30000


def test_profiles_are_isolated_between_users(client):
    a = register(client, email="a@example.org")
    b = register(client, email="b@example.org")
    client.put("/api/v1/profile", json=profile(full_name="Alice"), headers=a)
    assert client.get("/api/v1/profile", headers=b).status_code == 404
    client.put("/api/v1/profile", json=profile(full_name="Bob"), headers=b)
    assert client.get("/api/v1/profile", headers=a).get_json()["full_name"] == "Alice"


def test_client_cannot_supply_user_id(client, auth):
    resp = client.put("/api/v1/profile", json=profile(user_id="someone-else"), headers=auth)
    assert resp.status_code == 422


@pytest.mark.parametrize("override", [
    {"gpa": 4.5},  # above scale
    {"gpa": -1},
    {"gpa_scale": 0},
    {"funding_mode": "whatever"},
    {"english_test": None},  # score without test
    {"english_score": 12},  # out of range for IELTS
    {"gre_total": 200},
    {"annual_budget_usd": -5},
    {"full_name": ""},
])
def test_invalid_profiles_rejected(client, auth, override):
    assert client.put("/api/v1/profile", json=profile(**override), headers=auth).status_code == 422


def test_optional_fields_may_be_omitted(client, auth):
    minimal = {"full_name": "Min", "funding_mode": "funded_only", "gpa": 3.0, "gpa_scale": 4.0, "undergraduate_field": "Physics"}
    resp = client.put("/api/v1/profile", json=minimal, headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["english_test"] is None


def test_profile_requires_auth(client):
    assert client.put("/api/v1/profile", json=profile()).status_code == 401
