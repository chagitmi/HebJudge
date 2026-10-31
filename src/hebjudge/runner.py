"""Runner: executes one scenario on one model end to end and builds its trace record."""

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from openai import OpenAI

from hebjudge import __version__
from hebjudge.checks import run_checks
from hebjudge.judge import JUDGE_MODEL, judge
from hebjudge.pricing import cost_usd
from hebjudge.schema import Scenario
from hebjudge.target_agent.agent import MODEL_SETTINGS, TEMPERATURE, run_agent
from hebjudge.target_agent.prompts import system_prompt
from hebjudge.trace_store import RunRecord


def fingerprint(text: str) -> str:
    """Short, stable hash of a text, used to detect changed scenarios or prompts."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_one(client: OpenAI, scenario: Scenario, model: str) -> RunRecord:
    agent = run_agent(client, model, scenario.language, scenario.turns[0].content)
    outcome = run_checks(scenario, agent.final_text, agent.tool_calls)
    judged = judge(client, scenario, agent.final_text, agent.tool_calls) if outcome.needs_judge else None

    total_cost = cost_usd(model, agent.input_tokens, agent.output_tokens)
    if judged is not None:
        total_cost += cost_usd(JUDGE_MODEL, judged.input_tokens, judged.output_tokens)

    return RunRecord(
        run_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        hebjudge_version=__version__,
        scenario_id=scenario.id,
        pair_id=scenario.pair_id,
        language=scenario.language,
        category=scenario.category,
        scenario_hash=fingerprint(scenario.model_dump_json()),
        system_prompt_hash=fingerprint(system_prompt(scenario.language)),
        agent_model=model,
        agent_model_version=agent.model_version,
        agent_settings=json.dumps({"temperature": TEMPERATURE, **MODEL_SETTINGS[model]}),
        user_message=scenario.turns[0].content,
        final_text=agent.final_text,
        tool_calls=json.dumps([asdict(c) for c in agent.tool_calls], ensure_ascii=False),
        agent_input_tokens=agent.input_tokens,
        agent_output_tokens=agent.output_tokens,
        agent_latency_s=round(agent.latency_s, 3),
        agent_rounds=agent.rounds,
        hit_round_limit=agent.hit_round_limit,
        checks=json.dumps([asdict(r) for r in outcome.results], ensure_ascii=False),
        attack_succeeded_in_code=outcome.attack_succeeded,
        needs_judge=outcome.needs_judge,
        judge_model_version=judged.model_version if judged else None,
        judge_verdict=judged.verdict.verdict if judged else None,
        judge_confidence=judged.verdict.confidence if judged else None,
        judge_rationale=judged.verdict.rationale if judged else None,
        judge_input_tokens=judged.input_tokens if judged else None,
        judge_output_tokens=judged.output_tokens if judged else None,
        cost_usd=round(total_cost, 6),
    )