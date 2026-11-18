"""Reaching agents under test (v2): one interface, four adapters (D-40)."""

from typing import Any

from hebjudge.targets.adapters import (
    BuiltinStoreTarget,
    HttpTarget,
    OpenAICompatibleTarget,
    PythonTarget,
)
from hebjudge.targets.base import Target, TargetError, TargetReply
from hebjudge.targets.config import (
    BuiltinStoreConfig,
    HttpConfig,
    OpenAICompatibleConfig,
    PythonConfig,
    TargetFile,
    load_target_file,
)

__all__ = [
    "Target",
    "TargetError",
    "TargetFile",
    "TargetReply",
    "build_target",
    "load_target_file",
]

# The harmless message used to check a connection (`hebjudge target test`).
HELLO_MESSAGE = "שלום, מה אתה יכול לעשות?"


def build_target(target_file: TargetFile, client: Any | None = None) -> Target:
    """Create the adapter for a target file.

    `client` is an OpenAI client, used by the builtin and OpenAI-compatible adapters; if it is
    not given, one is created from the environment (the API key is never read from the file).
    """
    config = target_file.target
    name = target_file.name

    if isinstance(config, HttpConfig):
        return HttpTarget(name, config)
    if isinstance(config, PythonConfig):
        return PythonTarget(name, config)

    if client is None:
        import os

        from openai import OpenAI

        if isinstance(config, OpenAICompatibleConfig):
            api_key = os.environ.get(config.api_key_env)
            if not api_key:
                raise TargetError(f"environment variable {config.api_key_env} is not set")
            client = OpenAI(api_key=api_key, base_url=config.base_url)
        else:
            client = OpenAI()

    if isinstance(config, BuiltinStoreConfig):
        return BuiltinStoreTarget(name, config, client)
    if isinstance(config, OpenAICompatibleConfig):
        return OpenAICompatibleTarget(name, config, client)
    raise TargetError(f"unsupported adapter: {config.adapter}")
