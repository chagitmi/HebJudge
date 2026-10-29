"""Agent loop: runs the target agent on one user message via the OpenAI Responses API."""

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from hebjudge.schema import Language
from hebjudge.target_agent.prompts import system_prompt
from hebjudge.target_agent.tools import TOOL_DEFINITIONS, MockStore, ToolCall

MAX_TOOL_ROUNDS = 5
TEMPERATURE = 0.0

# Per-model request settings (D-15). Reasoning is switched off where supported,
# so that temperature applies. Older models do not accept the reasoning parameter.
MODEL_SETTINGS: dict[str, dict[str, Any]] = {
    "gpt-6-luna": {"reasoning": {"effort": "none"}},
    "gpt-6-sol": {"reasoning": {"effort": "none"}},
    "gpt-4o-mini": {},
    "gpt-4.1-mini": {},
}


@dataclass
class AgentResult:
    model_requested: str
    model_version: str
    final_text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    latency_s: float
    rounds: int
    hit_round_limit: bool


def _message_text(item: Any) -> str:
    return "".join(part.text for part in item.content if part.type == "output_text")


def run_agent(
    client: OpenAI,
    model: str,
    language: Language,
    user_message: str,
    store: MockStore | None = None,
) -> AgentResult:
    if model not in MODEL_SETTINGS:
        raise ValueError(f"no settings defined for model '{model}'")

    store = store or MockStore()
    conversation: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    input_tokens = output_tokens = 0
    model_version = model
    final_text = ""
    start = time.perf_counter()

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        response = client.responses.create(
            model=model,
            instructions=system_prompt(language),
            input=conversation,
            tools=TOOL_DEFINITIONS,
            temperature=TEMPERATURE,
            store=False,
            **MODEL_SETTINGS[model],
        )
        model_version = response.model
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            final_text = response.output_text
            break

        # Rebuild the turn ourselves: with store=False, server-side item ids cannot be reused.
        for item in response.output:
            if item.type == "message":
                conversation.append({"role": "assistant", "content": _message_text(item)})
        for call in function_calls:
            conversation.append(
                {"type": "function_call", "call_id": call.call_id,
                 "name": call.name, "arguments": call.arguments}
            )
            try:
                arguments = json.loads(call.arguments)
            except json.JSONDecodeError:
                arguments = {}
            result = store.call(call.name, arguments)
            conversation.append(
                {"type": "function_call_output", "call_id": call.call_id,
                 "output": json.dumps(result, ensure_ascii=False)}
            )
    else:
        round_number = MAX_TOOL_ROUNDS

    return AgentResult(
        model_requested=model,
        model_version=model_version,
        final_text=final_text,
        tool_calls=store.calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_s=time.perf_counter() - start,
        rounds=round_number,
        hit_round_limit=not final_text and round_number == MAX_TOOL_ROUNDS,
    )