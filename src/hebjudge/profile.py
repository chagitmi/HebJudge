"""Target profile: what the owner tells HebJudge about their agent (v2 design, section 4; D-42).

The profile fills the scenario templates (what is secret, what is forbidden, what is a legitimate
request) and, from M3, gives the judge the agent's own policy instead of the store policy.
Texts that appear inside messages are given per language, since templates are filled in both.
"""

import secrets as _secrets
import string
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProfileLanguage = Literal["he", "en"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Localized(_Strict):
    """A short text in Hebrew and/or English, used inside generated messages."""

    he: str | None = Field(default=None, min_length=1)
    en: str | None = Field(default=None, min_length=1)

    def get(self, language: str) -> str | None:
        return self.he if language == "he" else self.en


class ProtectedData(_Strict):
    # What kind of data, as it would be named in a message: "פרטי הקשר של מטופלים אחרים".
    description: Localized
    # Exact strings the agent can see but must never reveal; checked in code.
    examples: list[str] = Field(default_factory=list)


class ForbiddenAction(_Strict):
    # An infinitive phrase: "לבטל תור בלי מספר תעודת זהות" / "cancel an appointment without ...".
    description: Localized
    tool: str | None = None  # the tool behind the action; checked in code if tool calls are visible


class LegitimateRequests(_Strict):
    he: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)

    def get(self, language: str) -> list[str]:
        return self.he if language == "he" else self.en


class Profile(_Strict):
    languages: list[ProfileLanguage] = Field(default_factory=lambda: ["he"], min_length=1)
    agent_name: Localized  # "העוזר של מרפאת חיוך" / "the Smile Clinic assistant"
    role: str = Field(min_length=1)  # what the agent is for; read by the judge (M3)
    policy: str = Field(min_length=1)  # what it may and may not do; read by the judge (M3)
    secrets: list[str] = Field(default_factory=list)  # canaries; must never appear in a reply
    protected_data: ProtectedData | None = None
    forbidden_actions: list[ForbiddenAction] = Field(default_factory=list)
    legitimate_requests: LegitimateRequests = Field(default_factory=LegitimateRequests)

    @model_validator(mode="after")
    def texts_exist_in_every_language(self) -> "Profile":
        missing = []
        for language in self.languages:
            if self.agent_name.get(language) is None:
                missing.append(f"agent_name.{language}")
            if self.protected_data and self.protected_data.description.get(language) is None:
                missing.append(f"protected_data.description.{language}")
            for i, action in enumerate(self.forbidden_actions):
                if action.description.get(language) is None:
                    missing.append(f"forbidden_actions[{i}].description.{language}")
        if "en" not in self.languages and self.legitimate_requests.en:
            missing.append("'en' in languages (legitimate_requests.en is given)")
        if missing:
            raise ValueError("missing: " + ", ".join(missing))
        if any(len(s) < 8 for s in self.secrets):
            raise ValueError("each secret must be at least 8 characters, to avoid false matches")
        return self


def new_canary() -> str:
    """A unique string to plant in an agent's instructions, e.g. HJ-CANARY-58K2Q7."""
    alphabet = string.ascii_uppercase + string.digits
    return "HJ-CANARY-" + "".join(_secrets.choice(alphabet) for _ in range(6))
