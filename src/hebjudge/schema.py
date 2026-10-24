"""Scenario schema: definition and validation of HebJudge test scenarios."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

Language = Literal["he", "en"]
Category = Literal[
    "direct_injection",
    "indirect_injection",
    "leakage",
    "unauthorized_tool_action",
    "benign_control",
]
Severity = Literal["low", "medium", "high"]
HebrewTag = Literal[
    "code_switching",
    "no_niqqud",
    "rtl_ltr_mixing",
    "slang_transliteration",
]


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Turn(StrictModel):
    role: Literal["user"]
    content: str = Field(min_length=1)


class CanaryInOutput(StrictModel):
    type: Literal["canary_in_output"]
    value: str = Field(min_length=1)


class ToolCalled(StrictModel):
    type: Literal["tool_called"]
    tool: str = Field(min_length=1)


SuccessCheck = Annotated[CanaryInOutput | ToolCalled, Field(discriminator="type")]


class Scenario(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    pair_id: str | None = Field(default=None, pattern=ID_PATTERN)
    language: Language
    category: Category
    turns: list[Turn] = Field(min_length=1, max_length=1)  # single-turn in v1 (D-06)
    attacker_goal: str | None = None
    success_checks: list[SuccessCheck] = Field(default_factory=list)
    judge_rubric: str | None = None
    expected_safe_behavior: str = Field(min_length=1)
    severity: Severity
    hebrew_tags: list[HebrewTag] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_consistency(self) -> "Scenario":
        if self.pair_id is not None:
            expected_id = f"{self.pair_id}-{self.language}"
            if self.id != expected_id:
                raise ValueError(f"id must be '{expected_id}' for pair_id '{self.pair_id}'")
        elif self.language != "he":
            raise ValueError("only Hebrew scenarios may omit pair_id (Hebrew-only set)")

        if self.hebrew_tags and self.language != "he":
            raise ValueError("hebrew_tags are allowed only on Hebrew scenarios")

        if not self.success_checks and not self.judge_rubric:
            raise ValueError("a scenario needs at least one success_check or a judge_rubric")

        if self.category != "benign_control" and not self.attacker_goal:
            raise ValueError("attack scenarios must state an attacker_goal")

        return self


def load_scenario(path: str | Path) -> Scenario:
    """Load one scenario from a YAML file and validate it."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.model_validate(data)