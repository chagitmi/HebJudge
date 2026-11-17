"""Export the runs of one batch to a JSON Lines file, for analysis outside the HTML report.

Reads the local trace store only; makes no API calls.

Usage:
    python scripts/export_batch.py heonly-v1
    python scripts/export_batch.py heonly-v1 --out reports/heonly-v1-runs.jsonl
"""

import argparse
import json
from pathlib import Path

from hebjudge.trace_store import DEFAULT_DB_PATH, connect

FIELDS = [
    "run_id",
    "batch",
    "scenario_id",
    "category",
    "agent_model",
    "repeat_index",
    "user_message",
    "final_text",
    "tool_calls",
    "attack_succeeded_in_code",
    "needs_judge",
    "judge_verdict",
    "judge_rationale",
    "agent_input_tokens",
    "agent_output_tokens",
    "agent_latency_s",
    "cost_usd",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch")
    parser.add_argument("--out", default=None, help="Default: reports/<batch>-runs.jsonl")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    out = Path(args.out or f"reports/{args.batch}-runs.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(args.db)
    rows = conn.execute(
        "SELECT * FROM runs WHERE batch = ? ORDER BY scenario_id, agent_model, repeat_index",
        (args.batch,),
    ).fetchall()
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            record = {name: row[name] for name in FIELDS}
            record["tool_calls"] = json.loads(record["tool_calls"])
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Exported {len(rows)} runs from batch '{args.batch}' to {out}")


if __name__ == "__main__":
    main()
