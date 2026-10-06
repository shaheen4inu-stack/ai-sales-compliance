"""Input and output schemas, finding types, severities and routing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Finding type -> (category, severity, route). Severity and routing are fixed in code,
# never chosen by the model.
FINDING_TYPES: dict[str, tuple[str, str, str]] = {
    "absolute_guarantee": ("misleading_claim", "medium", "compliance"),
    "unapproved_claim": ("misleading_claim", "medium", "compliance"),
    "misstated_terms": ("misleading_claim", "medium", "compliance"),
    "false_competitor_statement": ("misleading_claim", "high", "compliance"),
    "solicited_competitor_pricing": ("competitor_information", "high", "compliance"),
    "used_volunteered_competitor_pricing": ("competitor_information", "high", "compliance"),
    "confidential_disclosure": ("confidential_information", "high", "compliance"),
    "possible_coordination": ("competition_law", "critical", "legal"),
}
GOOD_PRACTICE_TYPES = ("declined_competitor_information",)
# Findings whose quotes and explanations have money amounts and percentages masked.
MASKED_TYPES = {
    "solicited_competitor_pricing",
    "used_volunteered_competitor_pricing",
    "confidential_disclosure",
    "possible_coordination",
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

FindingType = Literal[tuple(FINDING_TYPES)]  # type: ignore[valid-type]
GoodPracticeType = Literal[GOOD_PRACTICE_TYPES]  # type: ignore[valid-type]


def _label(value):
    return None if value is None else str(value).strip().lower().replace(" ", "_").replace("-", "_")


class Turn(BaseModel):
    speaker: Literal["rep", "customer"]
    text: str

    @field_validator("speaker", mode="before")
    @classmethod
    def _speaker(cls, v):
        return _label(v)


class Call(BaseModel):
    """One sales call transcript."""

    id: str
    segments: dict[str, str] = Field(default_factory=dict, description="e.g. team, region; never individual reps")
    turns: list[Turn]


class ModelFinding(BaseModel):
    type: FindingType
    turn: int
    quote: str
    explanation: str

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        return _label(v)


class ModelGoodPractice(BaseModel):
    type: GoodPracticeType
    turn: int
    quote: str

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        return _label(v)


class ModelReview(BaseModel):
    summary: str
    findings: list[ModelFinding] = Field(default_factory=list)
    good_practice: list[ModelGoodPractice] = Field(default_factory=list)
