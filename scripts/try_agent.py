"""Run one scenario end to end, save the trace, and print a summary. Costs a fraction of a cent."""

import argparse
import json
import sys

from dotenv import load_dotenv
from openai import OpenAI

from hebjudge.runner import run_one
from hebjudge.schema import load_scenario
from hebjudge.trace_store import connect, save_run


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="Path to a scenario YAML file")
    parser.add_argument("--model", default="gpt-6-luna")
    args = parser.parse_args()

    load_dotenv()
    record = run_one(OpenAI(), load_scenario(args.scenario), args.model)
    with connect() as conn:
        save_run(conn, record)

    print(f"Saved run {record.run_id} for {record.scenario_id} on {record.agent_model_version}")
    for check in json.loads(record.checks):
        print(f"Check:   {check['check_type']}: {check['detail']}")
    print(f"Judge:   {record.judge_verdict} ({record.judge_confidence}): {record.judge_rationale}")
    print(f"Cost:    ${record.cost_usd:.6f}")
    print("--- Agent reply ---")
    print(record.final_text)


if __name__ == "__main__":
    main()