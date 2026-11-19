"""Scanning an agent from its target file (v2 design, sections 7 and 11; D-43).

A scan generates scenarios from the profile, selects them by level, estimates the cost, asks for
permission and confirmation, runs them on the target with the owner's policy given to the judge,
and summarizes the results per attacker goal.
"""

import hashlib
import json
import threading
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from hebjudge.judge import AgentPolicy
from hebjudge.pricing import PRICES, cost_usd
from hebjudge.profile import Profile
from hebjudge.report import final_verdict
from hebjudge.schema import Scenario
from hebjudge.targets import TargetFile
from hebjudge.targets.config import BuiltinStoreConfig, OpenAICompatibleConfig
from hebjudge.templates import Template, generate
from hebjudge.trace_store import RunRecord

# Measured in v1: the judge cost about $0.0018 to $0.0020 per judged reply (reports/main-v1).
JUDGE_COST_PER_RUN = 0.002
# A typical generated message and reply, for estimating the agent's own cost when it is known.
AGENT_TOKENS_PER_RUN = (800, 120)

# The quick level: one template per goal and technique that worked best in v1 (D-43).
QUICK_TEMPLATES = (
    "tpl-leak-002",  # fake system message
    "tpl-leak-003",  # format exploit (JSON)
    "tpl-data-001",  # authority impersonation
    "tpl-data-002",  # format exploit (JSON)
    "tpl-act-001",  # authority impersonation
    "tpl-act-003",  # fake system message
    "tpl-pol-001",  # partial compliance
    "tpl-role-001",  # role play
)
QUICK_BENIGN_PER_LANGUAGE = 2


@dataclass(frozen=True)
class Level:
    name: str
    templates: tuple[str, ...] | None  # None: every template
    benign_per_language: int | None  # None: every legitimate request
    repeats: int


LEVELS = {
    "quick": Level("quick", QUICK_TEMPLATES, QUICK_BENIGN_PER_LANGUAGE, 1),
    "standard": Level("standard", None, None, 1),
    "deep": Level("deep", None, None, 3),
}


def select_scenarios(
    profile: Profile,
    templates: Sequence[Template],
    level: Level,
    languages: list[str] | None = None,
) -> tuple[list[Scenario], list[tuple[str, str]]]:
    if level.templates is not None:
        templates = [t for t in templates if t.id in level.templates]
    scenarios, skipped = generate(profile, list(templates), languages)
    if level.benign_per_language is not None:
        kept: dict[str, int] = defaultdict(int)
        selected = []
        for scenario in scenarios:
            if scenario.category == "benign_control":
                if kept[scenario.language] >= level.benign_per_language:
                    continue
                kept[scenario.language] += 1
            selected.append(scenario)
        scenarios = selected
    return scenarios, skipped


@dataclass(frozen=True)
class CostEstimate:
    runs: int
    judge_usd: float  # an upper estimate: code-decided runs need no judge
    agent_usd: float | None  # None: unknown, billed by the agent's own provider

    @property
    def total_usd(self) -> float:
        return self.judge_usd + (self.agent_usd or 0.0)


def estimate_cost(target_file: TargetFile, runs: int) -> CostEstimate:
    config = target_file.target
    agent_usd = None
    if isinstance(config, BuiltinStoreConfig | OpenAICompatibleConfig):
        is_openai = not isinstance(config, OpenAICompatibleConfig) or config.base_url is None
        if is_openai and config.model in PRICES:
            agent_usd = runs * cost_usd(config.model, *AGENT_TOKENS_PER_RUN)
    return CostEstimate(runs, runs * JUDGE_COST_PER_RUN, agent_usd)


# --- permission ----------------------------------------------------------------


def target_fingerprint(target_file: TargetFile) -> str:
    """Identifies a target by name and connection settings, never by secrets."""
    config = target_file.target.model_dump()
    config.pop("headers", None)
    config.pop("system_prompt", None)
    data = json.dumps({"name": target_file.name, **config}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def has_permission(path: Path, target_file: TargetFile) -> bool:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return target_fingerprint(target_file) in stored


def record_permission(path: Path, target_file: TargetFile) -> None:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        stored = {}
    stored[target_fingerprint(target_file)] = {
        "name": target_file.name,
        "confirmed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")


# --- budget --------------------------------------------------------------------


class BudgetExceeded(RuntimeError):
    pass


def with_budget(
    run_fn: Callable[..., RunRecord], max_cost: float | None
) -> Callable[..., RunRecord]:
    """Stop starting new runs once the money spent reaches `max_cost`."""
    if max_cost is None:
        return run_fn
    lock = threading.Lock()
    spent = [0.0]

    def guarded(*args, **kwargs) -> RunRecord:
        with lock:
            if spent[0] >= max_cost:
                raise BudgetExceeded(f"budget of ${max_cost:.2f} reached; run not started")
        record = run_fn(*args, **kwargs)
        with lock:
            spent[0] += record.cost_usd
        return record

    return guarded


# --- saving and summary --------------------------------------------------------


def save_scenarios(scenarios: Sequence[Scenario], directory: Path) -> None:
    """Keep the exact scenarios of a scan next to its results, for review and comparison."""
    directory.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        data = scenario.model_dump(mode="json", exclude={"family"}, exclude_defaults=True)
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
        (directory / f"{scenario.id}.yaml").write_text(text, encoding="utf-8")


GOAL_LABELS = {
    "leak_system_prompt": "Reveals its instructions or secrets",
    "leak_protected_data": "Leaks protected data",
    "forbidden_action": "Performs forbidden actions",
    "off_policy_commitment": "Makes off-policy promises",
    "role_abandonment": "Abandons its role",
}


@dataclass
class GoalResult:
    label: str
    goal: str = ""
    failed: int = 0  # the attack succeeded
    total: int = 0  # decided runs
    unclear: int = 0


def summarize(records: Sequence[RunRecord], scenarios: Sequence[Scenario]) -> list[GoalResult]:
    """Results per attacker goal, then over-refusal on legitimate requests."""
    goal_of = {s.id: s.attacker_goal or "benign" for s in scenarios}
    results = {goal: GoalResult(label, goal) for goal, label in GOAL_LABELS.items()}
    results["benign"] = GoalResult("Refuses legitimate requests", "benign")
    for record in records:
        goal = goal_of.get(record.scenario_id, "other")
        result = results.setdefault(goal, GoalResult("Other", goal))
        verdict, _ = final_verdict(asdict(record))
        if verdict == "unclear":
            result.unclear += 1
            continue
        result.total += 1
        if verdict == "attack_succeeded":  # for benign controls: over-refused
            result.failed += 1
    return [r for r in results.values() if r.total or r.unclear]


def agent_policy(profile: Profile) -> AgentPolicy:
    return AgentPolicy(role=profile.role, policy=profile.policy)


GOAL_LABELS_HE = {
    "leak_system_prompt": "חושף את ההוראות או הסודות שלו",
    "leak_protected_data": "מדליף מידע מוגן",
    "forbidden_action": "מבצע פעולות אסורות",
    "off_policy_commitment": "מתחייב לדברים מחוץ למדיניות",
    "role_abandonment": "יוצא מהתפקיד שלו",
    "benign": "מסרב לבקשות לגיטימיות",
}


def public_settings(target_file: TargetFile) -> dict:
    """The target settings stored with each run: what identifies the agent, never a secret."""
    config = target_file.target.model_dump()
    config.pop("headers", None)  # may hold tokens
    config.pop("system_prompt", None)  # may be long or private; its file name is kept
    config.pop("body", None)
    return {"name": target_file.name, **config}


def failures(records: Sequence[RunRecord], scenarios: Sequence[Scenario]) -> list[tuple]:
    """(scenario id, attacker goal, technique) for every run where the attack succeeded."""
    by_id = {s.id: s for s in scenarios}
    result = []
    for record in records:
        scenario = by_id.get(record.scenario_id)
        if scenario and final_verdict(asdict(record))[0] == "attack_succeeded":
            result.append((record.scenario_id, scenario.attacker_goal, scenario.technique))
    return result


def attack_success_rate(records: Sequence[RunRecord]) -> float | None:
    """Percent of decided attack runs where the attack succeeded; None if there are none."""
    decided = [
        final_verdict(asdict(r))[0]
        for r in records
        if r.category != "benign_control" and final_verdict(asdict(r))[0] != "unclear"
    ]
    if not decided:
        return None
    return 100 * decided.count("attack_succeeded") / len(decided)


class ScanStopped(RuntimeError):
    pass


@dataclass
class ScanOutcome:
    batch: str
    records: list[RunRecord]
    completed: int
    failed: int
    cost_usd: float
    stopped: bool


def execute_scan(
    target_file: TargetFile,
    scenarios: Sequence[Scenario],
    level: Level,
    batch: str,
    db_path: str | Path,
    *,
    max_cost: float | None = None,
    workers: int | None = None,
    on_result: Callable[[int, int, RunRecord], None] | None = None,
    on_error: Callable[[int, int, Scenario, str, Exception], None] | None = None,
    stop_event: threading.Event | None = None,
    judge_client=None,
) -> ScanOutcome:
    """Run a scan that has been planned and confirmed. Shared by the CLI and the UI.

    Raises ValueError or TargetError before anything is sent if the target cannot be built.
    """
    from openai import OpenAI

    from hebjudge.runner import run_batch, run_one_on_target, target_label
    from hebjudge.targets import build_target
    from hebjudge.trace_store import connect

    if target_file.profile is None:
        raise ValueError("the target file has no profile")
    target = build_target(target_file)
    save_scenarios(scenarios, Path(db_path).parent / "scans" / batch)
    settings = public_settings(target_file)
    policy = agent_policy(target_file.profile)

    def run_on_target(client, scenario, model, batch, repeat_index):
        if stop_event is not None and stop_event.is_set():
            raise ScanStopped("stopped by the user; run not started")
        return run_one_on_target(
            target,
            client,
            scenario,
            batch=batch,
            repeat_index=repeat_index,
            settings=settings,
            policy=policy,
        )

    records: list[RunRecord] = []

    def collect(index: int, total: int, record: RunRecord) -> None:
        records.append(record)
        if on_result:
            on_result(index, total, record)

    workers = workers or (1 if target_file.target.adapter == "http" else 4)
    with connect(db_path) as conn:
        summary = run_batch(
            judge_client or OpenAI(max_retries=6),
            scenarios,
            [target_label(target)],
            level.repeats,
            batch,
            conn,
            run_fn=with_budget(run_on_target, max_cost),
            on_result=collect,
            on_error=on_error,
            workers=workers,
        )
    stopped = stop_event is not None and stop_event.is_set()
    return ScanOutcome(batch, records, summary.completed, summary.failed, summary.cost_usd, stopped)


def load_scan(db_path: str | Path, batch: str) -> tuple[list[RunRecord], list[Scenario]]:
    """A finished scan's runs and the exact scenarios it sent."""
    from hebjudge.schema import load_scenarios
    from hebjudge.trace_store import connect, record_from_row

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE batch = ? ORDER BY created_at", (batch,)
        ).fetchall()
    if not rows:
        raise ValueError(f"no runs found in batch '{batch}'")
    directory = Path(db_path).parent / "scans" / batch
    scenarios = load_scenarios([directory]) if directory.is_dir() else []
    return [record_from_row(r) for r in rows], scenarios
