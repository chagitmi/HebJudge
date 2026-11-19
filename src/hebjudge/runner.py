"""Runner: executes scenarios on models end to end and stores their trace records."""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from openai import OpenAI

from hebjudge import __version__
from hebjudge.checks import run_checks
from hebjudge.judge import JUDGE_MODEL, AgentPolicy, judge
from hebjudge.pricing import cost_usd
from hebjudge.schema import Scenario
from hebjudge.target_agent.agent import MODEL_SETTINGS, TEMPERATURE, run_agent
from hebjudge.target_agent.prompts import system_prompt
from hebjudge.target_agent.tools import MockStore
from hebjudge.targets import Target
from hebjudge.trace_store import RunRecord, save_run

# The development batch may be reused freely; any other batch name is protected (D-32).
DEV_BATCH = "dev"


def fingerprint(text: str) -> str:
    """Short, stable hash of a text, used to detect changed scenarios or prompts."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_one(
    client: OpenAI,
    scenario: Scenario,
    model: str,
    batch: str = DEV_BATCH,
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


TARGET_PREFIX = "target:"


def target_label(target: Target) -> str:
    """How an external target appears in the `agent_model` column and in reports."""
    return f"{TARGET_PREFIX}{target.name}"


def run_one_on_target(
    target: Target,
    judge_client: OpenAI,
    scenario: Scenario,
    batch: str = DEV_BATCH,
    repeat_index: int = 0,
    settings: dict | None = None,
    policy: AgentPolicy | None = None,
) -> RunRecord:
    """Run one scenario on an external target through its adapter (D-41).

    With `policy`, the judge uses the owner's role and policy instead of the store policy (D-43).

    Only the judge is billed by HebJudge; the target's own cost and tokens are unknown and stored
    as 0. Tool calls the target does not expose are stored as JSON `null`, not as an empty list.
    """
    if scenario.order_notes:
        raise ValueError(
            f"{scenario.id} needs order notes, which an external target cannot receive"
        )
    message = scenario.turns[0].content
    reply = target.send(message, session_id=f"hj-{uuid.uuid4().hex[:12]}")
    outcome = run_checks(scenario, reply.text, reply.tool_calls)
    policy_kwargs = {"policy": policy} if policy is not None else {}
    judged = (
        judge(judge_client, scenario, reply.text, reply.tool_calls, **policy_kwargs)
        if outcome.needs_judge
        else None
    )
    judge_cost = cost_usd(JUDGE_MODEL, judged.input_tokens, judged.output_tokens) if judged else 0.0
    settings_json = json.dumps(settings or {}, ensure_ascii=False, sort_keys=True)
    tool_calls = None if reply.tool_calls is None else [asdict(c) for c in reply.tool_calls]

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
        system_prompt_hash=fingerprint(settings_json),  # the target's settings, not a prompt
        agent_model=target_label(target),
        agent_model_version="",
        agent_settings=settings_json,
        user_message=message,
        final_text=reply.text,
        tool_calls=json.dumps(tool_calls, ensure_ascii=False),
        agent_input_tokens=0,
        agent_output_tokens=0,
        agent_latency_s=round(reply.latency_s, 3),
        agent_rounds=0,
        hit_round_limit=False,
        checks=json.dumps([asdict(r) for r in outcome.results], ensure_ascii=False),
        attack_succeeded_in_code=outcome.attack_succeeded,
        needs_judge=outcome.needs_judge,
        judge_model_version=judged.model_version if judged else None,
        judge_verdict=judged.verdict.verdict if judged else None,
        judge_confidence=judged.verdict.confidence if judged else None,
        judge_rationale=judged.verdict.rationale if judged else None,
        judge_input_tokens=judged.input_tokens if judged else None,
        judge_output_tokens=judged.output_tokens if judged else None,
        cost_usd=round(judge_cost, 6),
    )


@dataclass
class BatchSummary:
    completed: int = 0
    failed: int = 0
    skipped: int = 0  # already in the batch, when resuming
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
    workers: int = 1,
    resume: bool = False,
) -> BatchSummary:
    """Run every scenario on every model, `repeats` times, saving each record as it completes.

    Runs execute in `workers` threads; records are saved from the main thread only, so the
    database is never written concurrently. With `resume`, combinations already stored in the
    batch are skipped, so an interrupted batch can be continued.
    """
    unknown = [m for m in models if m not in MODEL_SETTINGS and not m.startswith(TARGET_PREFIX)]
    if unknown:
        raise ValueError(f"no settings defined for models: {unknown}")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    done = {
        (row[0], row[1], row[2])
        for row in conn.execute(
            "SELECT scenario_id, agent_model, repeat_index FROM runs WHERE batch = ?", (batch,)
        )
    }
    if done and not resume and batch != DEV_BATCH:
        raise ValueError(
            f"batch '{batch}' already has {len(done)} runs; "
            "use --resume to continue it, or choose a new batch name"
        )

    jobs = [(s, m, r) for s in scenarios for m in models for r in range(repeats)]
    summary = BatchSummary()
    if resume:
        pending = [(s, m, r) for s, m, r in jobs if (s.id, m, r) not in done]
        summary.skipped = len(jobs) - len(pending)
        jobs = pending

    total = len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_fn, client, s, m, batch=batch, repeat_index=r): (s, m)
            for s, m, r in jobs
        }
        for index, future in enumerate(as_completed(futures), start=1):
            scenario, model = futures[future]
            try:
                record = future.result()
            except Exception as exc:  # one failed run must not stop the batch
                summary.failed += 1
                if on_error:
                    on_error(index, total, scenario, model, exc)
                continue
            save_run(conn, record)
            summary.completed += 1
            summary.cost_usd += record.cost_usd
            if on_result:
                on_result(index, total, record)
    return summary
