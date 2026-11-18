"""The interface every tested agent is reached through (v2 design, section 3)."""

from dataclasses import dataclass
from typing import Protocol

from hebjudge.target_agent.tools import ToolCall


class TargetError(Exception):
    """The agent could not be reached, or its reply could not be read."""


@dataclass(frozen=True)
class TargetReply:
    text: str  # the agent's final reply
    tool_calls: list[ToolCall] | None  # None: tool calls are not visible to HebJudge
    latency_s: float
    raw: str  # the raw response, stored for review


class Target(Protocol):
    """An agent under test. One call to `send` is one single-turn conversation."""

    name: str

    def send(self, message: str, session_id: str) -> TargetReply: ...
