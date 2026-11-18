from app.config import Config
from app import create_app
from conftest import profile, register


def test_register_login_and_access_protected_route(client):
    headers = register(client)
    assert client.get("/api/v1/profile", headers=headers).status_code == 404  # authenticated, no profile yet
    login = client.post("/api/v1/auth/login", json={"email": "STUDENT@example.org ", "password": "correct-horse-battery"})
    assert login.status_code == 200
    assert login.get_json()["token_type"] == "Bearer"


def test_duplicate_email_conflicts_case_insensitively(client):
    register(client, email="dup@example.org")
    resp = client.post("/api/v1/auth/register", json={"email": "DUP@example.org", "password": "another-long-password"})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_TAKEN"


def test_weak_or_invalid_registration_rejected_without_echoing_input(client):
    resp = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "short"})
    assert resp.status_code == 422
    text = resp.get_data(as_text=True)
    assert "short" not in text and "not-an-email" not in text
    fields = {d["field"] for d in resp.get_json()["error"]["details"]}
    assert fields == {"email", "password"}


def test_unknown_fields_and_non_json_rejected(client):
    assert client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "long-enough-pass", "role": "admin"}).status_code == 422
    assert client.post("/api/v1/auth/register", data="plain", content_type="text/plain").status_code == 400


def test_login_errors_are_identical_for_unknown_email_and_wrong_password(client):
    register(client)
    wrong_pw = client.post("/api/v1/auth/login", json={"email": "student@example.org", "password": "wrong-password-1"})
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.org", "password": "wrong-password-1"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json() == unknown.get_json()


def test_login_throttles_after_repeated_failures_and_resets_on_success(client, config):
    register(client)
    body = {"email": "student@example.org", "password": "bad-password-xx"}
    for _ in range(config.login_max_failures):
        assert client.post("/api/v1/auth/login", json=body).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=body)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Even the correct password is refused while throttled.
    assert client.post("/api/v1/auth/login", json={**body, "password": "correct-horse-battery"}).status_code == 429


def test_failures_for_one_email_do_not_throttle_another(client, config):
    register(client)
    for _ in range(config.login_max_failures):
        client.post("/api/v1/auth/login", json={"email": "victim@example.org", "password": "bad-password-xx"})
    ok = client.post("/api/v1/auth/login", json={"email": "student@example.org", "password": "correct-horse-battery"})
    assert ok.status_code == 200


def test_protected_routes_require_valid_bearer_token(client):
    for headers in ({}, {"Authorization": "Bearer"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer not.a.jwt"}):
        resp = client.get("/api/v1/profile", headers=headers)
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_account_deletion_removes_data_and_invalidates_token(client, auth, conn):
    assert client.put("/api/v1/profile", json=profile(), headers=auth).status_code == 200
    assert client.delete("/api/v1/account", json={"password": "wrong-password-1"}, headers=auth).status_code == 403
    assert client.delete("/api/v1/account", json={"password": "correct-horse-battery"}, headers=auth).status_code == 204
    assert conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM student_profiles").fetchone()["n"] == 0
    assert client.get("/api/v1/profile", headers=auth).status_code == 401


def test_registration_rate_limited_per_client(config, conn):
    tight = Config(env="test", secret_key=config.secret_key, database_path=config.database_path, register_max_per_window=2)
    client = create_app(tight).test_client()
    codes = [client.post("/api/v1/auth/register", json={"email": f"u{i}@example.org", "password": "long-enough-pass"}).status_code
             for i in range(3)]
    assert codes == [201, 201, 429]


def test_security_headers_and_error_shape(client):
    resp = client.get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"
    assert "X-Request-ID" in resp.headers
    missing = client.get("/nope")
    assert missing.status_code == 404 and "error" in missing.get_json()


def test_app_refuses_to_start_with_pending_migrations(tmp_path):
    import pytest
    cfg = Config(env="test", secret_key="k" * 40, database_path=str(tmp_path / "fresh.db"))
    with pytest.raises(RuntimeError, match="Pending database migrations"):
        create_app(cfg)


def test_weak_secret_key_rejected():
    import pytest
    from app.config import ConfigError
    with pytest.raises(ConfigError):
        Config(env="test", secret_key="short", database_path="x.db")
