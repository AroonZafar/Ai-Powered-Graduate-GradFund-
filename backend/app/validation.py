"""Request-parsing helper shared by all route modules."""
from __future__ import annotations

from typing import TypeVar

from flask import request
from pydantic import BaseModel

from .errors import ApiError

M = TypeVar("M", bound=BaseModel)


def parse_json_body(model: type[M]) -> M:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object")
    return model.model_validate(data)
