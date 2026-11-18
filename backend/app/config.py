"""Application configuration, loaded from environment variables.

Secrets are never given defaults: a missing or weak SECRET_KEY stops startup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    env: str
    secret_key: str
    database_path: str
    jwt_ttl_seconds: int = 3600
    login_max_failures: int = 5
    login_window_seconds: int = 300
    register_max_per_window: int = 10
    register_window_seconds: int = 3600
    api_max_requests: int = 300
    api_window_seconds: int = 60
    stale_data_days: int = 120

    def __post_init__(self) -> None:
        if len(self.secret_key) < 32:
            raise ConfigError("SECRET_KEY must be set and at least 32 characters long")
        if self.jwt_ttl_seconds <= 0:
            raise ConfigError("jwt_ttl_seconds must be positive")

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            env=os.environ.get("APP_ENV", "development"),
            secret_key=os.environ.get("SECRET_KEY", ""),
            database_path=os.environ.get("DATABASE_PATH", "instance/gradfund.db"),
            jwt_ttl_seconds=int(os.environ.get("JWT_TTL_SECONDS", "3600")),
            stale_data_days=int(os.environ.get("STALE_DATA_DAYS", "120")),
        )
