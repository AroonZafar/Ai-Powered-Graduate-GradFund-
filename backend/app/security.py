"""Password hashing (scrypt, stdlib) and JWT access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import jwt

ISSUER = "gradfund"
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


class InvalidToken(Exception):
    pass


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _b64d(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=_b64d(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when an email is unknown so login timing does not reveal which emails exist.
DUMMY_HASH = hash_password("timing-equalisation-placeholder")


def issue_token(user_id: str, secret: str, ttl_seconds: int, now: int | None = None) -> str:
    issued = int(time.time()) if now is None else now
    claims = {"sub": user_id, "iss": ISSUER, "iat": issued, "exp": issued + ttl_seconds}
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> str:
    """Return the user id from a valid token, or raise InvalidToken."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidToken("missing subject")
    return sub
