"""Before and after: compare two scans of the same agent (v2 design, section 9; D-44).

Each scenario's verdict is the majority over its repeats. The comparison is fair only when both
scans sent exactly the same scenarios, so scenario fingerprints must match; otherwise it is
refused.
"""

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from hebjudge.report import final_verdict

CATEGORY_GOALS = {
    "leakage": "leakage",
    "unauthorized_tool_action": "forbidden_action",
    "direct_injection": "direct_injection",
    "indirect_injection": "indirect_injection",
}


@dataclass
class BatchVerdicts:
    verdict: dict[str, str]  # scenario id -> attack_succeeded / attack_failed / unclear / tie
    scenario_hash: dict[str, str]
    category: dict[str, str]


def batch_verdicts(conn: sqlite3.Connection, batch: str) -> BatchVerdicts:
    rows = conn.execute("SELECT * FROM runs WHERE batch = ?", (batch,)).fetchall()
    if not rows:
        raise ValueError(f"no runs found in batch '{batch}'")
    votes: dict[str, list[str]] = defaultdict(list)
    hashes: dict[str, str] = {}
    categories: dict[str, str] = {}
    for row in rows:
        votes[row["scenario_id"]].append(final_verdict(dict(row))[0])
        hashes[row["scenario_id"]] = row["scenario_hash"]
        categories[row["scenario_id"]] = row["category"]
    verdict = {}
    for scenario_id, values in votes.items():
        (top, count), *rest = Counter(values).most_common()
        verdict[scenario_id] = "tie" if rest and rest[0][1] == count else top
    return BatchVerdicts(verdict, hashes, categories)


@dataclass
class GoalCounts:
    before: int = 0  # scenarios where the attack succeeded (benign: over-refused)
    after: int = 0
    total: int = 0


@dataclass
class Comparison:
    common: list[str]
    fixed: list[str] = field(default_factory=list)  # failed before, safe after
    regressed: list[str] = field(default_factory=list)  # safe before, failed after
    other: list[tuple[str, str, str]] = field(default_factory=list)  # changes involving unclear
    by_goal: dict[str, GoalCounts] = field(default_factory=dict)
    only_before: list[str] = field(default_factory=list)
    only_after: list[str] = field(default_factory=list)


def compare(
    before: BatchVerdicts, after: BatchVerdicts, goals: dict[str, str] | None = None
) -> Comparison:
    """`goals` maps scenario ids to attacker goals; without it, categories are used."""
    common = sorted(set(before.verdict) & set(after.verdict))
    differ = [s for s in common if before.scenario_hash[s] != after.scenario_hash[s]]
    if differ:
        raise ValueError(
            "the scans did not send the same scenarios, so the comparison would not be fair: "
            + ", ".join(differ[:5])
            + (" ..." if len(differ) > 5 else "")
        )
    result = Comparison(
        common=common,
        only_before=sorted(set(before.verdict) - set(after.verdict)),
        only_after=sorted(set(after.verdict) - set(before.verdict)),
    )
    for scenario_id in common:
        a, b = before.verdict[scenario_id], after.verdict[scenario_id]
        if goals and scenario_id in goals:
            goal = goals[scenario_id]
        elif before.category[scenario_id] == "benign_control":
            goal = "benign"
        else:
            goal = CATEGORY_GOALS.get(before.category[scenario_id], "other")
        counts = result.by_goal.setdefault(goal, GoalCounts())
        counts.total += 1
        counts.before += a == "attack_succeeded"
        counts.after += b == "attack_succeeded"
        if a == b:
            continue
        if a == "attack_succeeded" and b == "attack_failed":
            result.fixed.append(scenario_id)
        elif a == "attack_failed" and b == "attack_succeeded":
            result.regressed.append(scenario_id)
        else:
            result.other.append((scenario_id, a, b))
    return result
