"""Re-evaluate stored runs with the current scenarios, checks and judge, without re-running the agent.

Each stored run is copied into a new batch. The agent's reply and tool calls stay exactly as they
were; the deterministic checks and the judge run again with the scenario as it is now. This changes
one variable at a time (rubric or judge), which is what calibration needs.
"""

import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

from hebjudge import __version__
from hebjudge.checks import run_checks
from hebjudge.judge import JUDGE_MODEL, JudgeResult, judge
from hebjudge.pricing import PRICES, cost_usd
from hebjudge.report import final_verdict
from hebjudge.runner import fingerprint
from hebjudge.schema import Scenario
from hebjudge.target_agent.tools import ToolCall
from hebjudge.trace_store import RunRecord, record_from_row, save_run

JudgeFn = Callable[..., JudgeResult]


@dataclass
class RejudgeSummary:
    judged: int = 0  # sent to the judge again
    decided_in_code: int = 0  # decided by the checks, no judge call
    skipped: int = 0  # scenario no longer exists
    failed: int = 0
    changed: int = 0  # final verdict differs from the original run
    judge_cost_usd: float = 0.0


def rejudge_run(
    client,
    record: RunRecord,
    scenario: Scenario,
    new_batch: str,
    judge_fn: JudgeFn = judge,
) -> tuple[RunRecord, float]:
    """Re-evaluate one stored run. Returns the new record and the cost of the judge call."""
    stored = json.loads(record.tool_calls)
    calls = None if stored is None else [ToolCall(**c) for c in stored]
    outcome = run_checks(scenario, record.final_text, calls)
    judged = judge_fn(client, scenario, record.final_text, calls) if outcome.needs_judge else None

    judge_cost = cost_usd(JUDGE_MODEL, judged.input_tokens, judged.output_tokens) if judged else 0.0
    agent_cost = (
        cost_usd(record.agent_model, record.agent_input_tokens, record.agent_output_tokens)
        if record.agent_model in PRICES  # an external target's own cost is unknown (D-41)
        else 0.0
    )

    new = replace(
        record,
        run_id=uuid.uuid4().hex,
        batch=new_batch,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        hebjudge_version=__version__,
        scenario_hash=fingerprint(scenario.model_dump_json()),
        checks=json.dumps([asdict(r) for r in outcome.results], ensure_ascii=False),
        attack_succeeded_in_code=outcome.attack_succeeded,
        needs_judge=outcome.needs_judge,
        judge_model_version=judged.model_version if judged else None,
        judge_verdict=judged.verdict.verdict if judged else None,
        judge_confidence=judged.verdict.confidence if judged else None,
        judge_rationale=judged.verdict.rationale if judged else None,
        judge_input_tokens=judged.input_tokens if judged else None,
        judge_output_tokens=judged.output_tokens if judged else None,
        cost_usd=round(agent_cost + judge_cost, 6),
        rejudged_from=record.run_id,
    )
    return new, judge_cost


def rejudge_batch(
    client,
    conn: sqlite3.Connection,
    source_batch: str,
    new_batch: str,
    scenarios: Mapping[str, Scenario],
    only: set[str] | None = None,
    judge_fn: JudgeFn = judge,
    on_result: Callable[[RunRecord, RunRecord], None] | None = None,
    on_error: Callable[[RunRecord, Exception], None] | None = None,
) -> RejudgeSummary:
    """Copy every run of `source_batch` into `new_batch`, re-evaluated with current scenarios."""
    if source_batch == new_batch:
        raise ValueError("the new batch must have a different name from the source batch")
    if conn.execute("SELECT 1 FROM runs WHERE batch = ? LIMIT 1", (new_batch,)).fetchone():
        raise ValueError(f"batch '{new_batch}' already exists; choose a new name")
    rows = conn.execute(
        "SELECT * FROM runs WHERE batch = ? ORDER BY created_at", (source_batch,)
    ).fetchall()
    if not rows:
        raise ValueError(f"no runs found in batch '{source_batch}'")

    summary = RejudgeSummary()
    for row in rows:
        record = record_from_row(row)
        if only and record.scenario_id not in only:
            continue
        scenario = scenarios.get(record.scenario_id)
        if scenario is None:
            summary.skipped += 1
            continue
        try:
            new, judge_cost = rejudge_run(client, record, scenario, new_batch, judge_fn)
        except Exception as exc:  # one failed call must not stop the batch
            summary.failed += 1
            if on_error:
                on_error(record, exc)
            continue
        save_run(conn, new)
        summary.judge_cost_usd += judge_cost
        if new.needs_judge:
            summary.judged += 1
        else:
            summary.decided_in_code += 1
        if final_verdict(asdict(new))[0] != final_verdict(asdict(record))[0]:
            summary.changed += 1
        if on_result:
            on_result(record, new)
    return summary
