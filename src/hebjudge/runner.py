"""Runner: executes scenarios on models end to end and stores their trace records."""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from openai import OpenAI

from hebjudge import __version__
from hebjudge.checks import run_checks
from hebjudge.judge import JUDGE_MODEL, judge
from hebjudge.pricing import cost_usd
from hebjudge.schema import Scenario
from hebjudge.target_agent.agent import MODEL_SETTINGS, TEMPERATURE, run_agent
from hebjudge.target_agent.prompts import system_prompt
from hebjudge.target_agent.tools import MockStore
from hebjudge.trace_store import RunRecord, save_run


def fingerprint(text: str) -> str:
    """Short, stable hash of a text, used to detect changed scenarios or prompts."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_one(
    client: OpenAI,
    scenario: Scenario,
    model: str,
    batch: str = "dev",
    repeat_index: int = 0,
) -> RunRecord:
    store = MockStore(order_notes=dict(scenario.order_notes))
    agent = run_agent(client, model, scenario.language, scenario.turns[0].content, store=store)
    outcome = run_checks(scenario, agent.final_text, agent.tool_calls)
    judged = (
        judge(client, scenario, agent.final_text, agent.tool_calls) if outcome.needs_judge else None
    )

    total_cost = cost_usd(model, agent.input_tokens, agent.output_tokens)
    if judged is not None:
        total_cost += cost_usd(JUDGE_MODEL, judged.input_tokens, judged.output_tokens)

    return RunRecord(
        run_id=uuid.uuid4().hex,
        batch=batch,
        repeat_index=repeat_index,
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


@dataclass
class BatchSummary:
    completed: int = 0
    failed: int = 0
    cost_usd: float = 0.0


def run_batch(
    client: OpenAI | None,
    scenarios: Sequence[Scenario],
    models: Sequence[str],
    repeats: int,
    batch: str,
    conn: sqlite3.Connection,
    run_fn: Callable[..., RunRecord] = run_one,
    on_result: Callable[[int, int, RunRecord], None] | None = None,
    on_error: Callable[[int, int, Scenario, str, Exception], None] | None = None,
) -> BatchSummary:
    """Run every scenario on every model, `repeats` times, saving each record as it completes."""
    unknown = [m for m in models if m not in MODEL_SETTINGS]
    if unknown:
        raise ValueError(f"no settings defined for models: {unknown}")

    jobs = [(s, m, r) for s in scenarios for m in models for r in range(repeats)]
    summary = BatchSummary()
    for index, (scenario, model, repeat_index) in enumerate(jobs, start=1):
        try:
            record = run_fn(client, scenario, model, batch=batch, repeat_index=repeat_index)
        except Exception as exc:  # one failed run must not stop the batch
            summary.failed += 1
            if on_error:
                on_error(index, len(jobs), scenario, model, exc)
            continue
        save_run(conn, record)
        summary.completed += 1
        summary.cost_usd += record.cost_usd
        if on_result:
            on_result(index, len(jobs), record)
    return summary
