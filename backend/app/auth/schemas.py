from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Strict):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 254 or not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        # Upper bound limits scrypt CPU/memory abuse from huge inputs.
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v


class LoginRequest(_Strict):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not v or len(v) > 128:
            raise ValueError("Invalid password")
        return v


class DeleteAccountRequest(_Strict):
    password: str

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not v or len(v) > 128:
            raise ValueError("Invalid password")
        return v
