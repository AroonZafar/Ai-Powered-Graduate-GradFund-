from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Valid score ranges per test.
_ENGLISH_RANGES = {"ielts": (0.0, 9.0), "toefl_ibt": (0.0, 120.0), "duolingo": (10.0, 160.0)}


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=120)
    funding_mode: Literal["funded_only", "open_to_unfunded"]
    gpa: float = Field(ge=0)
    gpa_scale: float = Field(gt=0, le=100)
    undergraduate_field: str = Field(min_length=1, max_length=100)
    english_test: Optional[Literal["ielts", "toefl_ibt", "duolingo"]] = None
    english_score: Optional[float] = None
    gre_total: Optional[int] = Field(default=None, ge=260, le=340)
    annual_budget_usd: Optional[int] = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _cross_field(self) -> "ProfileIn":
        if self.gpa > self.gpa_scale:
            raise ValueError("gpa cannot exceed gpa_scale")
        if (self.english_test is None) != (self.english_score is None):
            raise ValueError("english_test and english_score must be provided together")
        if self.english_test is not None:
            lo, hi = _ENGLISH_RANGES[self.english_test]
            if not lo <= self.english_score <= hi:
                raise ValueError(f"english_score must be between {lo:g} and {hi:g} for {self.english_test}")
        return self
