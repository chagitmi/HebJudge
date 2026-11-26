"""Target configuration: how to reach an agent, read from the `target:` section of a YAML file.

Secrets (API keys, tokens) are never written in the file. They are referenced by the name of an
environment variable, either in `api_key_env` or as `${VAR}` inside an HTTP header (D-40).
"""

import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hebjudge.profile import Profile

ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MESSAGE_PLACEHOLDER = "{{message}}"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BuiltinStoreConfig(_Strict):
    """The v1 mock store agent (D-40): a demo target with known behavior."""

    adapter: Literal["builtin_store"]
    model: str = "gpt-4o-mini"
    language: Literal["he", "en"] = "he"


class OpenAICompatibleConfig(_Strict):
    """An agent that is a system prompt on a model behind an OpenAI-compatible chat API."""

    adapter: Literal["openai_compatible"]
    model: str
    base_url: str | None = None  # None: the OpenAI API itself
    api_key_env: str = "OPENAI_API_KEY"
    system_prompt: str | None = None
    system_prompt_file: str | None = None
    temperature: float = 0.0

    @model_validator(mode="after")
    def one_system_prompt(self) -> "OpenAICompatibleConfig":
        if (self.system_prompt is None) == (self.system_prompt_file is None):
            raise ValueError("give exactly one of system_prompt or system_prompt_file")
        return self


class HttpConfig(_Strict):
    """Any agent behind an HTTP endpoint that takes JSON and returns JSON."""

    adapter: Literal["http"]
    url: str = Field(pattern=r"^https?://")
    method: Literal["POST", "PUT"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any]  # JSON request template; must contain "{{message}}" somewhere
    reply_path: str  # where the reply text is in the response, e.g. "choices.0.message.content"
    tool_calls_path: str | None = None  # where a list of {name, arguments} is, if exposed
    timeout_s: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def body_has_message(self) -> "HttpConfig":
        if MESSAGE_PLACEHOLDER not in yaml.safe_dump(self.body, allow_unicode=True):
            raise ValueError(f"body must contain the placeholder {MESSAGE_PLACEHOLDER}")
        return self


class PythonConfig(_Strict):
    """A Python function: 'package.module:function' or 'path/to/file.py:function'."""

    adapter: Literal["python"]
    function: str = Field(pattern=r"^.+:[A-Za-z_][A-Za-z0-9_]*$")


TargetConfig = Annotated[
    BuiltinStoreConfig | OpenAICompatibleConfig | HttpConfig | PythonConfig,
    Field(discriminator="adapter"),
]


class TargetFile(_Strict):
    """A target file: how to reach the agent and, optionally, its profile (D-42)."""

    name: str = Field(min_length=1)
    profile: Profile | None = None
    target: TargetConfig


def load_target_file(path: str | Path) -> TargetFile:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping with 'name' and 'target'")
    try:
        return TargetFile.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def expand_env(text: str, environ: dict[str, str] | None = None) -> str:
    """Replace every ${VAR} with the value of the environment variable VAR."""
    env = os.environ if environ is None else environ

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ValueError(f"environment variable {name} is not set")
        return env[name]

    return ENV_REF.sub(replace, text)


_SECRET_NAME = re.compile(r"auth|token|key|secret|password|cookie|session", re.IGNORECASE)
_SECRET_VALUE = re.compile(
    r"\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE
)

LITERAL_SECRET_MESSAGE = (
    "בכותרות יש טוקן או מפתח שכתוב כמו שהוא, והוא היה נשמר בקובץ. "
    "כותבים במקומו שם של משתנה סביבה, למשל ‎Bearer ${MY_TOKEN}‎, "
    "ומגדירים את MY_TOKEN במחשב לפני שמפעילים את HebJudge."
)


def literal_secret_headers(headers: dict[str, str]) -> list[str]:
    """Header names whose value looks like a secret typed in as is, instead of ${VAR} (D-49).

    Only for saving from the UI: a file written by hand still loads, so nothing that worked
    before stops working.
    """
    found = []
    for name, value in headers.items():
        text = str(value)
        if "${" in text:
            continue
        if (_SECRET_NAME.search(name) and text.strip()) or _SECRET_VALUE.search(text):
            found.append(name)
    return found
