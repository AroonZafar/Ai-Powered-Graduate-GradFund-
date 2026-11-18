import json

import pytest
from pydantic import ValidationError

from app import cli
from app.programs import repository
from app.programs.schemas import ProgramImport
from conftest import profile, program_payload, register


def imp(conn, **overrides):
    return repository.import_program(conn, ProgramImport.model_validate(program_payload(**overrides)))


def publish(conn, pid):
    repository.publish_program(conn, pid, "Reviewer One")


# ---- importer validation -------------------------------------------------

def test_import_rejects_known_fact_without_source():
    payload = program_payload()
    del payload["sources"]["tuition"]
    with pytest.raises(ValidationError, match="Missing source"):
        ProgramImport.model_validate(payload)


def test_import_rejects_source_without_url_or_date():
    payload = program_payload()
    payload["sources"]["funding"] = {"url": "https://example.edu/x"}
    with pytest.raises(ValidationError):
        ProgramImport.model_validate(payload)


def test_import_rejects_future_verification_date_and_bad_urls():
    payload = program_payload()
    payload["sources"]["funding"]["verified_on"] = "2999-01-01"
    with pytest.raises(ValidationError):
        ProgramImport.model_validate(payload)
    with pytest.raises(ValidationError):
        ProgramImport.model_validate(program_payload(application_url="javascript:alert(1)"))


def test_unknown_values_need_no_source_but_sources_for_unset_facts_are_rejected():
    payload = program_payload(ms_assistantships="unknown", funding=[])
    del payload["sources"]["assistantships"], payload["sources"]["funding"]
    ProgramImport.model_validate(payload)  # valid: nothing known, nothing to source
    payload["sources"]["funding"] = {"url": "https://example.edu/x", "verified_on": "2026-10-01"}
    with pytest.raises(ValidationError, match="not set"):
        ProgramImport.model_validate(payload)


def test_inconsistent_assistantship_claims_rejected():
    with pytest.raises(ValidationError, match="none_listed"):
        ProgramImport.model_validate(program_payload(ms_assistantships="none_listed"))


def test_cost_requires_cost_year():
    with pytest.raises(ValidationError, match="cost_year"):
        ProgramImport.model_validate(program_payload(cost_year=None))


def test_unknown_import_fields_rejected():
    with pytest.raises(ValidationError):
        ProgramImport.model_validate(program_payload(guaranteed_funding=True))


# ---- review / publish workflow ------------------------------------------

def test_imports_are_drafts_and_invisible_until_published(conn):
    pid, outcome = imp(conn)
    assert outcome == "created"
    assert repository.list_published(conn) == []
    assert repository.get_published(conn, pid) is None
    publish(conn, pid)
    assert [p.id for p in repository.list_published(conn)] == [pid]


def test_publish_requires_reviewer_and_complete_sources(conn):
    pid, _ = imp(conn)
    with pytest.raises(repository.PublishBlocked, match="reviewer"):
        repository.publish_program(conn, pid, "   ")
    conn.execute("DELETE FROM field_sources WHERE program_id = ? AND field_key = 'tuition'", (pid,))
    with pytest.raises(repository.PublishBlocked, match="tuition"):
        publish(conn, pid)
    assert repository.get_published(conn, pid) is None


def test_publish_unknown_program(conn):
    with pytest.raises(repository.ProgramNotFound):
        publish(conn, "missing")


def test_reimport_unchanged_keeps_published_and_changed_returns_to_draft(conn):
    pid, _ = imp(conn)
    publish(conn, pid)
    same_id, outcome = imp(conn)
    assert (same_id, outcome) == (pid, "unchanged")
    assert repository.get_published(conn, pid) is not None
    changed_id, outcome = imp(conn, tuition_intl_usd_per_year=25000)
    assert (changed_id, outcome) == (pid, "updated")
    assert repository.get_published(conn, pid) is None  # must be re-reviewed
    row = conn.execute("SELECT reviewed_by, reviewed_at FROM programs WHERE id = ?", (pid,)).fetchone()
    assert row["reviewed_by"] is None and row["reviewed_at"] is None


def test_reimport_replaces_children_without_duplicates(conn):
    pid, _ = imp(conn)
    imp(conn, deadlines=[{"intake": "spring", "deadline_date": "2026-12-01"}])
    rows = conn.execute("SELECT intake FROM program_deadlines WHERE program_id = ?", (pid,)).fetchall()
    assert [r["intake"] for r in rows] == ["spring"]
    assert conn.execute("SELECT count(*) AS n FROM universities").fetchone()["n"] == 1


def test_record_verified_on_is_oldest_source_date(conn):
    payload = program_payload()
    payload["sources"]["tuition"]["verified_on"] = "2026-03-02"
    pid, _ = repository.import_program(conn, ProgramImport.model_validate(payload))
    assert conn.execute("SELECT verified_on FROM programs WHERE id = ?", (pid,)).fetchone()["verified_on"] == "2026-03-02"


# ---- CLI -----------------------------------------------------------------

def test_cli_import_is_all_or_nothing(tmp_path, monkeypatch, config, conn, capsys):
    monkeypatch.setenv("SECRET_KEY", config.secret_key)
    monkeypatch.setenv("DATABASE_PATH", config.database_path)
    bad = program_payload(degree_name="MS Bad")
    del bad["sources"]["tuition"]
    path = tmp_path / "batch.json"
    path.write_text(json.dumps([program_payload(), bad]))
    assert cli.main(["import-programs", str(path)]) == 1
    assert conn.execute("SELECT count(*) AS n FROM programs").fetchone()["n"] == 0
    assert "Missing source" in capsys.readouterr().err


def test_cli_import_list_and_publish(tmp_path, monkeypatch, config, conn, capsys):
    monkeypatch.setenv("SECRET_KEY", config.secret_key)
    monkeypatch.setenv("DATABASE_PATH", config.database_path)
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(program_payload()))
    assert cli.main(["import-programs", str(path)]) == 0
    pid = conn.execute("SELECT id FROM programs").fetchone()["id"]
    assert cli.main(["list-drafts"]) == 0 and pid in capsys.readouterr().out
    assert cli.main(["publish-program", pid, "--reviewer", "Reviewer One"]) == 0
    assert cli.main(["publish-program", "nope", "--reviewer", "R"]) == 1
    assert conn.execute("SELECT status FROM programs WHERE id = ?", (pid,)).fetchone()["status"] == "published"


# ---- API -----------------------------------------------------------------

def seed(conn):
    good, _ = imp(conn)
    unfundable, _ = imp(conn, university_name="Fixture Tech", degree_name="MS in Cybersecurity", field="cybersecurity",
                        program_type="non_thesis", ms_assistantships="none_listed", funding=[],
                        sources={k: {"url": "https://example.edu/s", "verified_on": "2026-10-01"} for k in (
                            "program_type", "duration", "tuition", "living_cost", "gre_policy", "min_gpa", "english",
                            "intl_admission", "contact_faculty_policy", "assistantships", "deadlines")})
    draft, _ = imp(conn, university_name="Draft College", degree_name="MS Draft")
    publish(conn, good)
    publish(conn, unfundable)
    return good, unfundable, draft


def test_programs_api_requires_auth(client):
    assert client.get("/api/v1/programs").status_code == 401
    assert client.get("/api/v1/programs/abc").status_code == 401


def test_empty_catalogue_returns_empty_list_not_fake_data(client, auth):
    body = client.get("/api/v1/programs", headers=auth).get_json()
    assert body["data"] == [] and body["meta"]["total"] == 0


def test_list_without_profile_has_no_fit_and_hides_drafts(client, auth, conn):
    seed(conn)
    body = client.get("/api/v1/programs", headers=auth).get_json()
    assert body["meta"] == {"page": 1, "per_page": 20, "total": 2, "sort": "university", "profile_complete": False}
    assert all(p["fit"] is None for p in body["data"])
    assert {p["university"]["name"] for p in body["data"]} == {"Testville State University", "Fixture Tech"}


def test_fit_is_attached_and_sorted_best_first_with_profile(client, auth, conn):
    seed(conn)
    client.put("/api/v1/profile", json=profile(), headers=auth)
    data = client.get("/api/v1/programs", headers=auth).get_json()["data"]
    assert [p["fit"]["verdict"] for p in data] == ["good_fit", "poor_fit"]
    poor_codes = {f["code"] for f in data[1]["fit"]["findings"]}
    assert {"NO_MASTERS_FUNDING", "NON_THESIS_PROGRAM"} <= poor_codes
    assert data[0]["sources"]["tuition"]["url"] == "https://example.edu/source"


def test_filters_search_and_verdict(client, auth, conn):
    seed(conn)
    client.put("/api/v1/profile", json=profile(), headers=auth)
    names = lambda qs: [p["degree_name"] for p in client.get(f"/api/v1/programs?{qs}", headers=auth).get_json()["data"]]
    assert names("field=cybersecurity") == ["MS in Cybersecurity"]
    assert names("program_type=thesis") == ["MS in Artificial Intelligence"]
    assert names("verdict=poor_fit") == ["MS in Cybersecurity"]
    assert names("q=fixture") == ["MS in Cybersecurity"]
    assert names("q=%25") == []  # LIKE wildcards are escaped, not interpreted


def test_fit_sort_and_filter_require_a_profile(client, auth, conn):
    seed(conn)
    for qs in ("sort=fit", "verdict=good_fit"):
        resp = client.get(f"/api/v1/programs?{qs}", headers=auth)
        assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "PROFILE_REQUIRED"


def test_pagination_and_query_validation(client, auth, conn):
    seed(conn)
    page1 = client.get("/api/v1/programs?per_page=1&page=1", headers=auth).get_json()
    page2 = client.get("/api/v1/programs?per_page=1&page=2", headers=auth).get_json()
    assert page1["meta"]["total"] == 2 and len(page1["data"]) == len(page2["data"]) == 1
    assert page1["data"][0]["id"] != page2["data"][0]["id"]
    assert client.get("/api/v1/programs?page=3&per_page=1", headers=auth).get_json()["data"] == []
    for bad in ("per_page=500", "page=0", "sort=drop", "field=nope", "unexpected=1"):
        assert client.get(f"/api/v1/programs?{bad}", headers=auth).status_code == 422


def test_sorting_by_cost_and_deadline(client, auth, conn):
    seed(conn)
    client.put("/api/v1/profile", json=profile(), headers=auth)
    assert client.get("/api/v1/programs?sort=cost", headers=auth).status_code == 200
    assert client.get("/api/v1/programs?sort=deadline", headers=auth).status_code == 200


def test_program_detail_and_draft_is_not_found(client, auth, conn):
    good, _, draft = seed(conn)
    assert client.get(f"/api/v1/programs/{good}", headers=auth).get_json()["id"] == good
    assert client.get(f"/api/v1/programs/{draft}", headers=auth).status_code == 404
    assert client.get("/api/v1/programs/does-not-exist", headers=auth).status_code == 404


def test_fit_reflects_each_users_own_profile(client, conn):
    seed(conn)
    funded = register(client, email="funded@example.org")
    rich = register(client, email="rich@example.org")
    client.put("/api/v1/profile", json=profile(), headers=funded)
    client.put("/api/v1/profile", json=profile(funding_mode="open_to_unfunded", annual_budget_usd=100000), headers=rich)
    verdicts = lambda h: {p["degree_name"]: p["fit"]["verdict"] for p in client.get("/api/v1/programs", headers=h).get_json()["data"]}
    assert verdicts(funded)["MS in Cybersecurity"] == "poor_fit"
    assert verdicts(rich)["MS in Cybersecurity"] == "fit_with_caveats"  # still non-thesis, but not blocked
