"""Compare the verdicts of two batches scenario by scenario. Reads the local store only; no API calls.

Each side is a batch, optionally limited to one model. Per scenario, the side's verdict is the
majority over its repeats (as in the report). Used for the M1 regression check (D-41): the same
agent reached directly and over HTTP should agree on almost every scenario.

Usage:
    python scripts/compare_batches.py main-v1 --model-a gpt-4o-mini m1-regression
"""

import argparse
from collections import Counter, defaultdict

from hebjudge.report import final_verdict
from hebjudge.trace_store import DEFAULT_DB_PATH, connect


def verdicts(conn, batch: str, model: str | None) -> dict[str, str]:
    query = "SELECT * FROM runs WHERE batch = ?"
    params: list = [batch]
    if model:
        query += " AND agent_model = ?"
        params.append(model)
    by_scenario: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(query, params).fetchall():
        verdict, _ = final_verdict(dict(row))
        by_scenario[row["scenario_id"]].append(verdict)
    result = {}
    for scenario_id, values in by_scenario.items():
        (top, count), *rest = Counter(values).most_common()
        tied = rest and rest[0][1] == count
        result[scenario_id] = "tie" if tied else top
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch_a")
    parser.add_argument("batch_b")
    parser.add_argument("--model-a", help="Only runs of this model in batch A")
    parser.add_argument("--model-b", help="Only runs of this model in batch B")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    with connect(args.db) as conn:
        a = verdicts(conn, args.batch_a, args.model_a)
        b = verdicts(conn, args.batch_b, args.model_b)

    common = sorted(set(a) & set(b))
    if not common:
        print("No scenarios in common.")
        return
    differ = [s for s in common if a[s] != b[s]]
    agree = len(common) - len(differ)
    print(f"Scenarios in both: {len(common)}")
    print(f"Same verdict:      {agree} ({100 * agree / len(common):.0f}%)")
    print(f"Different:         {len(differ)}")
    for scenario_id in differ:
        print(f"  {scenario_id}: {a[scenario_id]} -> {b[scenario_id]}")


if __name__ == "__main__":
    main()
