from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..db import get_db
from ..errors import ApiError
from ..security import issue_token
from ..validation import parse_json_body
from . import service
from .guard import require_auth
from .schemas import DeleteAccountRequest, LoginRequest, RegisterRequest

bp = Blueprint("auth", __name__, url_prefix="/api/v1")


def _client_key() -> str:
    return request.remote_addr or "unknown"


def _limiter(name: str):
    return current_app.extensions["limiters"][name]


def _token_response(user_id: str, status: int):
    cfg = current_app.extensions["gradfund_config"]
    token = issue_token(user_id, cfg.secret_key, cfg.jwt_ttl_seconds)
    return jsonify({"access_token": token, "token_type": "Bearer", "expires_in": cfg.jwt_ttl_seconds}), status


@bp.post("/auth/register")
def register():
    limiter = _limiter("register")
    wait = limiter.retry_after(_client_key())
    if wait:
        raise ApiError(429, "RATE_LIMITED", "Too many registrations; try again later",
                       headers={"Retry-After": str(wait)})
    limiter.record(_client_key())
    body = parse_json_body(RegisterRequest)
    try:
        user_id = service.register_user(get_db(), body.email, body.password)
    except service.EmailTaken:
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists")
    return _token_response(user_id, 201)


@bp.post("/auth/login")
def login():
    body = parse_json_body(LoginRequest)
    limiter = _limiter("login")
    key = f"{_client_key()}|{body.email}"
    wait = limiter.retry_after(key)
    if wait:
        raise ApiError(429, "RATE_LIMITED", "Too many failed attempts; try again later",
                       headers={"Retry-After": str(wait)})
    try:
        user_id = service.authenticate(get_db(), body.email, body.password)
    except service.BadCredentials:
        limiter.record(key)
        raise ApiError(401, "BAD_CREDENTIALS", "Incorrect email or password")
    limiter.clear(key)
    return _token_response(user_id, 200)


@bp.delete("/account")
@require_auth
def delete_account():
    """Permanently delete the account and all data tied to it."""
    body = parse_json_body(DeleteAccountRequest)
    db = get_db()
    if not service.verify_user_password(db, g.user_id, body.password):
        raise ApiError(403, "BAD_PASSWORD", "Password confirmation failed")
    service.delete_user(db, g.user_id)
    return "", 204
