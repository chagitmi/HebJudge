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
    failed: int = 0  # the attack succeeded
    total: int = 0  # decided runs
    unclear: int = 0


def summarize(records: Sequence[RunRecord], scenarios: Sequence[Scenario]) -> list[GoalResult]:
    """Results per attacker goal, then over-refusal on legitimate requests."""
    goal_of = {s.id: s.attacker_goal or "benign" for s in scenarios}
    results = {goal: GoalResult(label) for goal, label in GOAL_LABELS.items()}
    results["benign"] = GoalResult("Refuses legitimate requests")
    for record in records:
        result = results.setdefault(goal_of.get(record.scenario_id, "other"), GoalResult("Other"))
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
