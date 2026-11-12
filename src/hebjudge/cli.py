"""Command-line interface: hebjudge run / report."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hebjudge import __version__
from hebjudge.trace_store import DEFAULT_DB_PATH, RunRecord, connect

DEFAULT_REPORT_PATH = Path("data/runs/report.html")


def _print_details(record: RunRecord) -> None:
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


def _run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv
    from openai import OpenAI

    from hebjudge.report import final_verdict, verdict_label
    from hebjudge.runner import run_batch
    from hebjudge.schema import load_scenarios

    if args.repeats < 1:
        print("Error: --repeats must be at least 1")
        return 1
    try:
        scenarios = load_scenarios(args.scenarios)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 1
    if not scenarios:
        print("Error: no scenario files found")
        return 1

    total = len(scenarios) * len(args.models) * args.repeats
    print(
        f"Batch '{args.batch}': {len(scenarios)} scenarios x {len(args.models)} models "
        f"x {args.repeats} repeats = {total} runs"
    )

    def on_result(index: int, total: int, record: RunRecord) -> None:
        if total == 1:
            _print_details(record)
            return
        verdict, decided_by = final_verdict(asdict(record))
        print(
            f"[{index}/{total}] {record.scenario_id} | {record.agent_model} "
            f"#{record.repeat_index + 1} | {verdict_label(asdict(record))} ({decided_by}) "
            f"| ${record.cost_usd:.4f}"
        )

    def on_error(index: int, total: int, scenario, model: str, exc: Exception) -> None:
        print(f"[{index}/{total}] {scenario.id} | {model} | ERROR: {exc}")

    load_dotenv()
    try:
        with connect(args.db) as conn:
            summary = run_batch(
                OpenAI(),
                scenarios,
                args.models,
                args.repeats,
                args.batch,
                conn,
                on_result=on_result,
                on_error=on_error,
            )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(
        f"Done: {summary.completed} completed, {summary.failed} failed, "
        f"total cost ${summary.cost_usd:.4f}"
    )
    return 0 if summary.failed == 0 else 1


def _report(args: argparse.Namespace) -> int:
    from hebjudge.report import write_report

    if not Path(args.db).exists():
        print(f"No trace database at {args.db}. Run a scenario first.")
        return 1
    with connect(args.db) as conn:
        path = write_report(conn, args.out, batch=args.batch)
    print(f"Report written to {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="hebjudge", description="Hebrew agent evaluation & red-teaming"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run scenarios end to end and save the traces")
    run_parser.add_argument("scenarios", nargs="+", help="Scenario YAML files or directories")
    run_parser.add_argument("--models", nargs="+", default=["gpt-6-luna"])
    run_parser.add_argument("--repeats", type=int, default=1)
    run_parser.add_argument("--batch", default="dev", help="Label stored with every run (D-26)")
    run_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))

    report_parser = sub.add_parser("report", help="Build an HTML report from saved traces")
    report_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    report_parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    report_parser.add_argument("--batch", default=None, help="Only include runs from this batch")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "report":
        return _report(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
