"""The four adapters (v2 design, section 3; D-40).

Each adapter turns one user message into one `TargetReply`. Adapters do not judge anything;
checks and the judge work on the reply exactly as in v1.
"""

import importlib
import importlib.util
import inspect
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hebjudge.target_agent.tools import MockStore, ToolCall
from hebjudge.targets.base import TargetError, TargetReply
from hebjudge.targets.config import (
    MESSAGE_PLACEHOLDER,
    BuiltinStoreConfig,
    HttpConfig,
    OpenAICompatibleConfig,
    PythonConfig,
    expand_env,
)

SESSION_PLACEHOLDER = "{{session_id}}"


# --- helpers -----------------------------------------------------------------


def extract(data: Any, path: str) -> Any:
    """Follow a dotted path into JSON data: "choices.0.message.content"."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise TargetError(f"path '{path}' not found in the response (failed at '{part}')")
    return current


def render(template: Any, message: str, session_id: str) -> Any:
    """Fill {{message}} and {{session_id}} in every string of a JSON template."""
    if isinstance(template, str):
        return template.replace(MESSAGE_PLACEHOLDER, message).replace(
            SESSION_PLACEHOLDER, session_id
        )
    if isinstance(template, dict):
        return {key: render(value, message, session_id) for key, value in template.items()}
    if isinstance(template, list):
        return [render(item, message, session_id) for item in template]
    return template


def parse_tool_calls(items: Any) -> list[ToolCall]:
    """Read a list of {"name": ..., "arguments": {...} or JSON string} into ToolCalls."""
    if not isinstance(items, list):
        raise TargetError("tool calls must be a list")
    calls = []
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            raise TargetError("each tool call needs at least a 'name'")
        arguments = item.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"_raw": arguments}
        calls.append(ToolCall(str(item["name"]), dict(arguments), item.get("result") or {}))
    return calls


# --- adapters ----------------------------------------------------------------


class BuiltinStoreTarget:
    """The v1 mock store agent. Tool calls are fully visible."""

    def __init__(self, name: str, config: BuiltinStoreConfig, client: Any) -> None:
        self.name = name
        self.config = config
        self.client = client

    def send(self, message: str, session_id: str) -> TargetReply:
        from hebjudge.target_agent.agent import run_agent

        result = run_agent(
            self.client, self.config.model, self.config.language, message, store=MockStore()
        )
        raw = json.dumps(
            {"model": result.model_version, "text": result.final_text}, ensure_ascii=False
        )
        return TargetReply(result.final_text, result.tool_calls, result.latency_s, raw)


class OpenAICompatibleTarget:
    """A system prompt on a model, through the Chat Completions API. The agent has no tools."""

    def __init__(self, name: str, config: OpenAICompatibleConfig, client: Any) -> None:
        self.name = name
        self.config = config
        self.client = client
        if config.system_prompt_file is not None:
            self.system_prompt = Path(config.system_prompt_file).read_text(encoding="utf-8")
        else:
            self.system_prompt = config.system_prompt or ""

    def send(self, message: str, session_id: str) -> TargetReply:
        start = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message},
                ],
                temperature=self.config.temperature,
            )
        except Exception as exc:  # any client or network error
            raise TargetError(f"request failed: {exc}") from exc
        text = response.choices[0].message.content or ""
        raw = json.dumps(
            {"model": getattr(response, "model", ""), "text": text}, ensure_ascii=False
        )
        return TargetReply(text, [], time.perf_counter() - start, raw)


class HttpTarget:
    """Any JSON-over-HTTP agent. Tool calls are visible only if `tool_calls_path` is set."""

    def __init__(
        self, name: str, config: HttpConfig, environ: dict[str, str] | None = None
    ) -> None:
        self.name = name
        self.config = config
        # Resolve ${VAR} references now, so a missing variable fails before any message is sent.
        self.headers = {k: expand_env(v, environ) for k, v in config.headers.items()}
        self.headers.setdefault("Content-Type", "application/json; charset=utf-8")

    def send(self, message: str, session_id: str) -> TargetReply:
        body = json.dumps(render(self.config.body, message, session_id), ensure_ascii=False)
        request = urllib.request.Request(
            self.config.url,
            data=body.encode("utf-8"),
            headers=self.headers,
            method=self.config.method,
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise TargetError(f"HTTP {exc.code} from {self.config.url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TargetError(f"could not reach {self.config.url}: {exc}") from exc
        latency = time.perf_counter() - start

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TargetError("the response is not JSON") from exc
        text = extract(data, self.config.reply_path)
        if not isinstance(text, str):
            raise TargetError(f"'{self.config.reply_path}' is not text")
        tool_calls = None
        if self.config.tool_calls_path is not None:
            tool_calls = parse_tool_calls(extract(data, self.config.tool_calls_path))
        return TargetReply(text, tool_calls, latency, raw)


def load_function(spec: str) -> Callable[..., Any]:
    """Load 'package.module:function' or 'path/to/file.py:function'."""
    location, _, attribute = spec.rpartition(":")
    if location.endswith(".py"):
        path = Path(location)
        if not path.is_file():
            raise TargetError(f"file not found: {path}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        if module_spec is None or module_spec.loader is None:
            raise TargetError(f"cannot load {path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(location)
        except ImportError as exc:
            raise TargetError(f"cannot import {location}: {exc}") from exc
    function = getattr(module, attribute, None)
    if not callable(function):
        raise TargetError(f"{spec} is not a function")
    return function


class PythonTarget:
    """A Python function taking (message) or (message, session_id).

    It returns the reply text, or a dict with "text" and optionally "tool_calls".
    """

    def __init__(self, name: str, config: PythonConfig) -> None:
        self.name = name
        self.function = load_function(config.function)
        self.takes_session = len(inspect.signature(self.function).parameters) >= 2

    def send(self, message: str, session_id: str) -> TargetReply:
        start = time.perf_counter()
        try:
            if self.takes_session:
                result = self.function(message, session_id)
            else:
                result = self.function(message)
        except Exception as exc:
            raise TargetError(f"the function raised {type(exc).__name__}: {exc}") from exc
        latency = time.perf_counter() - start

        if isinstance(result, str):
            return TargetReply(
                result, None, latency, json.dumps({"text": result}, ensure_ascii=False)
            )
        if isinstance(result, dict) and isinstance(result.get("text"), str):
            tool_calls = None
            if "tool_calls" in result:
                tool_calls = parse_tool_calls(result["tool_calls"])
            raw = json.dumps(result, ensure_ascii=False, default=str)
            return TargetReply(result["text"], tool_calls, latency, raw)
        raise TargetError("the function must return text, or a dict with a 'text' field")
