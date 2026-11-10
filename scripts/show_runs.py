"""Print stored runs for one scenario (optionally one model), newest first."""

import argparse
import sqlite3
import sys

from hebjudge.trace_store import DEFAULT_DB_PATH


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_id", help="For example inj-indirect-001-he")
    parser.add_argument("--model", help="Only runs of this model")
    parser.add_argument("--limit", type=int, default=1, help="How many runs to show")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    sql = (
        "SELECT created_at, agent_model, tool_calls, final_text, judge_rationale "
        "FROM runs WHERE scenario_id = ?"
    )
    params: list = [args.scenario_id]
    if args.model:
        sql += " AND agent_model = ?"
        params.append(args.model)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(args.limit)

    rows = sqlite3.connect(args.db).execute(sql, params).fetchall()
    if not rows:
        print("No runs found.")
        return
    for created_at, model, tool_calls, final_text, rationale in rows:
        print(f"=== {created_at} | {model}")
        print(f"Tools: {tool_calls}")
        print(final_text)
        if rationale:
            print(f"Judge: {rationale}")
        print()


if __name__ == "__main__":
    main()
