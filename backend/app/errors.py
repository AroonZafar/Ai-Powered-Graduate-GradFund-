"""Consistent JSON error responses. No internal details leak to clients."""
from __future__ import annotations

import logging

from flask import Flask, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger("gradfund.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None,
                 headers: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def _body(code: str, message: str, details: list | None = None) -> dict:
    err: dict = {"code": code, "message": message}
    if details:
        err["details"] = details
    return {"error": err}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return jsonify(_body(exc.code, exc.message, exc.details)), exc.status, exc.headers

    @app.errorhandler(ValidationError)
    def _validation_error(exc: ValidationError):
        # Only field paths and messages are returned; submitted values are never echoed back.
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return jsonify(_body("VALIDATION_ERROR", "Request validation failed", details)), 422

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        return jsonify(_body(exc.name.upper().replace(" ", "_"), exc.description or exc.name)), exc.code

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        log.exception("unhandled_exception")
        return jsonify(_body("INTERNAL_ERROR", "An unexpected error occurred")), 500
