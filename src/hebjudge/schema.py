"""Scenario schema: definition and validation of HebJudge test scenarios."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from hebjudge.target_agent.tools import default_orders

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
Tone = Literal["polite", "casual", "aggressive"]
HebrewTag = Literal[
    "code_switching",
    "no_niqqud",
    "rtl_ltr_mixing",
    "slang_transliteration",
]

# Attack techniques and their families (D-18). The family is derived, never written by hand.
TECHNIQUE_FAMILIES: dict[str, str] = {
    "authority_impersonation": "social_engineering",
    "emotional_pressure": "social_engineering",
    "instruction_override": "instruction_override",
    "fake_system_message": "instruction_override",
    "refusal_suppression": "instruction_override",
    "fake_conversation": "instruction_override",
    "role_play": "framing",
    "hypothetical_fiction": "framing",
    "encoding": "obfuscation",
    "hidden_text": "obfuscation",
    "payload_splitting": "obfuscation",
    "translation_trick": "obfuscation",
    "keyboard_layout": "obfuscation",
    "atbash": "obfuscation",
    "bidi_control": "obfuscation",
    "format_exploit": "format_exploit",
}
HEBREW_ONLY_TECHNIQUES = {"keyboard_layout", "atbash", "bidi_control"}


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
    arguments: dict[str, str] | None = None  # if set, only calls with these argument values count


SuccessCheck = Annotated[CanaryInOutput | ToolCalled, Field(discriminator="type")]


class Scenario(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    pair_id: str | None = Field(default=None, pattern=ID_PATTERN)
    language: Language
    category: Category
    technique: str | None = None
    tone: Tone  # how the customer speaks (D-23)
    turns: list[Turn] = Field(min_length=1, max_length=1)  # single-turn in v1 (D-06)
    order_notes: dict[str, str] = Field(default_factory=dict)  # planted into the store (D-21)
    attacker_goal: str | None = None
    success_checks: list[SuccessCheck] = Field(default_factory=list)
    judge_rubric: str | None = None
    expected_safe_behavior: str = Field(min_length=1)
    severity: Severity
    hebrew_tags: list[HebrewTag] = Field(default_factory=list)

    @computed_field
    @property
    def family(self) -> str | None:
        return TECHNIQUE_FAMILIES.get(self.technique) if self.technique else None

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

        if self.category == "benign_control":
            if self.technique is not None:
                raise ValueError("benign_control scenarios have no technique")
        else:
            if not self.attacker_goal:
                raise ValueError("attack scenarios must state an attacker_goal")
            if self.technique is None:
                raise ValueError("attack scenarios must state a technique")

        if self.technique is not None:
            if self.technique not in TECHNIQUE_FAMILIES:
                raise ValueError(
                    f"unknown technique '{self.technique}'; allowed: {sorted(TECHNIQUE_FAMILIES)}"
                )
            if self.technique in HEBREW_ONLY_TECHNIQUES and (
                self.language != "he" or self.pair_id is not None
            ):
                raise ValueError(f"technique '{self.technique}' is for Hebrew-only scenarios")

        unknown_orders = set(self.order_notes) - set(default_orders())
        if unknown_orders:
            raise ValueError(f"order_notes refer to unknown orders: {sorted(unknown_orders)}")
        if self.category == "indirect_injection" and not self.order_notes:
            raise ValueError("indirect_injection scenarios must plant at least one order note")

        return self


def load_scenario(path: str | Path) -> Scenario:
    """Load one scenario from a YAML file and validate it."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.model_validate(data)
