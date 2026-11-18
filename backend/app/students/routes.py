from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..auth.guard import require_auth
from ..db import get_db
from ..errors import ApiError
from ..validation import parse_json_body
from . import repository
from .schemas import ProfileIn

bp = Blueprint("students", __name__, url_prefix="/api/v1")


def _profile_json(row) -> dict:
    return {k: row[k] for k in row.keys()}


@bp.get("/profile")
@require_auth
def get_profile():
    row = repository.get_profile(get_db(), g.user_id)
    if row is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "Complete your profile first")
    return jsonify(_profile_json(row))


@bp.put("/profile")
@require_auth
def put_profile():
    data = parse_json_body(ProfileIn)
    db = get_db()
    repository.upsert_profile(db, g.user_id, data)
    return jsonify(_profile_json(repository.get_profile(db, g.user_id)))
