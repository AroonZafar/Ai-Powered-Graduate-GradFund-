"""Authentication guard. The user id always comes from the verified token, never the client."""
from __future__ import annotations

from functools import wraps

from flask import current_app, g, request

from ..db import get_db
from ..errors import ApiError
from ..security import InvalidToken, decode_token
from .service import user_exists

_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise ApiError(401, "UNAUTHENTICATED", "Authentication required", headers=_CHALLENGE)
        cfg = current_app.extensions["gradfund_config"]
        try:
            user_id = decode_token(token.strip(), cfg.secret_key)
        except InvalidToken:
            raise ApiError(401, "INVALID_TOKEN", "Invalid or expired token", headers=_CHALLENGE)
        # Rejects tokens belonging to deleted accounts.
        if not user_exists(get_db(), user_id):
            raise ApiError(401, "INVALID_TOKEN", "Invalid or expired token", headers=_CHALLENGE)
        g.user_id = user_id
        return view(*args, **kwargs)

    return wrapper
