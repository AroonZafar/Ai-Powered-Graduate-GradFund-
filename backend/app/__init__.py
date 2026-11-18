"""Application factory."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Optional

from flask import Flask, g, jsonify, request

from .config import Config
from .db import close_db, connect, pending_migrations
from .errors import ApiError, register_error_handlers
from .ratelimit import RateLimiter

log = logging.getLogger("gradfund.request")


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def create_app(config: Optional[Config] = None, today: Callable[[], date] = _utc_today) -> Flask:
    config = config or Config.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # Refuse to start against an out-of-date schema; migrations are applied explicitly via the CLI.
    conn = connect(config.database_path)
    try:
        pending = pending_migrations(conn)
    finally:
        conn.close()
    if pending:
        raise RuntimeError(f"Pending database migrations: {', '.join(pending)}. Run `python -m app.cli migrate`.")

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    app.json.sort_keys = False
    app.extensions["gradfund_config"] = config
    app.extensions["today"] = today
    app.extensions["limiters"] = {
        "login": RateLimiter(config.login_max_failures, config.login_window_seconds),
        "register": RateLimiter(config.register_max_per_window, config.register_window_seconds),
        "api": RateLimiter(config.api_max_requests, config.api_window_seconds),
    }

    register_error_handlers(app)
    app.teardown_appcontext(close_db)

    @app.before_request
    def _before():
        g.request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex
        g.started = time.monotonic()
        limiter = app.extensions["limiters"]["api"]
        key = request.remote_addr or "unknown"
        wait = limiter.retry_after(key)
        if wait:
            raise ApiError(429, "RATE_LIMITED", "Too many requests", headers={"Retry-After": str(wait)})
        limiter.record(key)

    @app.after_request
    def _after(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Cache-Control"] = "no-store"
        if config.env == "production":
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Never log bodies, headers, or emails: only request metadata and the opaque user id.
        log.info("request_id=%s method=%s path=%s status=%s ms=%d user=%s",
                 getattr(g, "request_id", "-"), request.method, request.path, resp.status_code,
                 int((time.monotonic() - getattr(g, "started", time.monotonic())) * 1000),
                 getattr(g, "user_id", "-"))
        return resp

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    from .auth.routes import bp as auth_bp
    from .programs.routes import bp as programs_bp
    from .students.routes import bp as students_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(programs_bp)
    return app
