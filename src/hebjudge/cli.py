"""Command-line interface: hebjudge run / report."""

import argparse
import json
import sys
from pathlib import Path

from hebjudge import __version__
from hebjudge.trace_store import DEFAULT_DB_PATH, connect, save_run

DEFAULT_REPORT_PATH = Path("data/runs/report.html")


def _run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv
    from openai import OpenAI

    from hebjudge.runner import run_one
    from hebjudge.schema import load_scenario

    load_dotenv()
    record = run_one(OpenAI(), load_scenario(args.scenario), args.model)
    with connect(args.db) as conn:
        save_run(conn, record)

    print(f"Saved run {record.run_id} for {record.scenario_id} on {record.agent_model_version}")
    calls = [(c["name"], c["arguments"]) for c in json.loads(record.tool_calls)]
    print(f"Tools:   {calls or 'none'}")
    for check in json.loads(record.checks):
        print(f"Check:   {check['check_type']}: {check['detail']}")
    if record.judge_verdict is not None:
        print(
            f"Judge:   {record.judge_verdict} ({record.judge_confidence}): {record.judge_rationale}"
        )
    print(f"Cost:    ${record.cost_usd:.6f}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from hebjudge.report import write_report

    if not Path(args.db).exists():
        print(f"No trace database at {args.db}. Run a scenario first.")
        return 1
    with connect(args.db) as conn:
        path = write_report(conn, args.out)
    print(f"Report written to {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="hebjudge", description="Hebrew agent evaluation & red-teaming"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run one scenario end to end and save the trace")
    run_parser.add_argument("scenario", help="Path to a scenario YAML file")
    run_parser.add_argument("--model", default="gpt-6-luna")
    run_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))

    report_parser = sub.add_parser("report", help="Build an HTML report from saved traces")
    report_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    report_parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "report":
        return _report(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
