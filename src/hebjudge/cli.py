"""Command-line interface: hebjudge run / rejudge / calibrate / report / target."""

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

    if args.workers < 1:
        print("Error: --workers must be at least 1")
        return 1
    total = len(scenarios) * len(args.models) * args.repeats
    print(
        f"Batch '{args.batch}': {len(scenarios)} scenarios x {len(args.models)} models "
        f"x {args.repeats} repeats = {total} runs, {args.workers} in parallel"
    )

    def on_result(index: int, total: int, record: RunRecord) -> None:
        if total == 1:
            _print_details(record)
            return
        _, decided_by = final_verdict(asdict(record))
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
                OpenAI(max_retries=6),  # the SDK backs off and retries rate limits and timeouts
                scenarios,
                args.models,
                args.repeats,
                args.batch,
                conn,
                on_result=on_result,
                on_error=on_error,
                workers=args.workers,
                resume=args.resume,
            )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(
        f"Done: {summary.completed} completed, {summary.failed} failed, "
        f"{summary.skipped} already done (skipped), total cost ${summary.cost_usd:.4f}"
    )
    return 0 if summary.failed == 0 else 1


def _rejudge(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv
    from openai import OpenAI

    from hebjudge.rejudge import rejudge_batch
    from hebjudge.report import verdict_label
    from hebjudge.schema import load_scenarios

    if not Path(args.db).exists():
        print(f"No trace database at {args.db}. Run a scenario first.")
        return 1
    try:
        scenarios = {s.id: s for s in load_scenarios(args.scenarios)}
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 1

    def on_result(old: RunRecord, new: RunRecord) -> None:
        before, after = verdict_label(asdict(old)), verdict_label(asdict(new))
        if before != after:
            print(f"CHANGED  {new.scenario_id} | {new.agent_model} | {before} -> {after}")
            if new.judge_rationale:
                print(f"         {new.judge_rationale}")

    def on_error(old: RunRecord, exc: Exception) -> None:
        print(f"ERROR    {old.scenario_id} | {old.agent_model} | {exc}")

    load_dotenv()
    try:
        with connect(args.db) as conn:
            summary = rejudge_batch(
                OpenAI(),
                conn,
                args.batch,
                args.new_batch,
                scenarios,
                only=set(args.only) if args.only else None,
                on_result=on_result,
                on_error=on_error,
            )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(
        f"Done: {summary.judged} re-judged, {summary.decided_in_code} decided in code, "
        f"{summary.skipped} skipped (scenario not found), {summary.failed} failed. "
        f"{summary.changed} verdicts changed. Judge cost ${summary.judge_cost_usd:.4f}"
    )
    return 0 if summary.failed == 0 else 1


DEFAULT_LABELS_DIR = Path("data/labels")
DEFAULT_LABELING_DIR = Path("data/runs/calibration")


def _write_labeling_page(batch: str, sample_file: dict, scenarios_args: list[str], db: str) -> Path:
    from hebjudge.calibration import labeling_items, render_labeling_html
    from hebjudge.schema import load_scenarios

    scenarios = {s.id: s for s in load_scenarios(scenarios_args)}
    with connect(db) as conn:
        rows = conn.execute("SELECT * FROM runs WHERE batch = ?", (batch,)).fetchall()
    rows_by_id = {r["run_id"]: r for r in rows}
    items = labeling_items(sample_file["items"], rows_by_id, scenarios)
    DEFAULT_LABELING_DIR.mkdir(parents=True, exist_ok=True)
    page_path = DEFAULT_LABELING_DIR / f"label-{batch}.html"
    page_path.write_text(render_labeling_html(items, sample_file["sample_id"]), encoding="utf-8")
    return page_path


def _calibrate_page(args: argparse.Namespace) -> int:
    sample_path = DEFAULT_LABELS_DIR / f"sample-{args.batch}.json"
    if not sample_path.exists() or not Path(args.db).exists():
        print(f"Not found: {sample_path} or {args.db}. Run 'hebjudge calibrate sample' first.")
        return 1
    sample_file = json.loads(sample_path.read_text(encoding="utf-8"))
    page_path = _write_labeling_page(args.batch, sample_file, args.scenarios, args.db)
    print(f"Labeling page rebuilt from the existing sample: {page_path}")
    print("Labels already entered in the browser are kept.")
    return 0


def _calibrate_sample(args: argparse.Namespace) -> int:
    from hebjudge.calibration import select_sample
    from hebjudge.schema import load_scenarios

    if not Path(args.db).exists():
        print(f"No trace database at {args.db}.")
        return 1
    sample_path = DEFAULT_LABELS_DIR / f"sample-{args.batch}.json"
    if sample_path.exists() and not args.force:
        print(f"{sample_path} already exists. The sample must not change once labeling has begun.")
        print("Use --force only if you have not started labeling.")
        return 1

    scenarios = {s.id: s for s in load_scenarios(args.scenarios)}
    with connect(args.db) as conn:
        rows = conn.execute("SELECT * FROM runs WHERE batch = ?", (args.batch,)).fetchall()
    rows = [r for r in rows if r["scenario_id"] in scenarios]
    if not rows:
        print(f"No runs found in batch '{args.batch}'.")
        return 1

    sample = select_sample(rows, per_language=args.per_language, seed=args.seed)
    rows_by_id = {r["run_id"]: r for r in rows}
    sample_id = f"{args.batch}-seed{args.seed}"

    DEFAULT_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    sample_path.write_text(
        json.dumps(
            {"sample_id": sample_id, "batch": args.batch, "seed": args.seed, "items": sample},
            indent=2,
        ),
        encoding="utf-8",
    )
    page_path = _write_labeling_page(
        args.batch,
        {"sample_id": sample_id, "items": sample},
        args.scenarios,
        args.db,
    )

    by_stratum: dict[tuple, int] = {}
    for entry in sample:
        r = rows_by_id[entry["run_id"]]
        key = (r["language"], r["judge_verdict"])
        by_stratum[key] = by_stratum.get(key, 0) + 1
    print(f"Sample of {len(sample)} judged runs written to {sample_path}")
    for (language, verdict), count in sorted(by_stratum.items()):
        print(f"  {language}, judge {verdict}: {count}")
    print(f"Labeling page written to {page_path}")
    return 0


def _calibrate_score(args: argparse.Namespace) -> int:
    from hebjudge.calibration import score

    sample_path = Path(args.sample or DEFAULT_LABELS_DIR / f"sample-{args.batch}.json")
    for path in (Path(args.db), sample_path, Path(args.labels)):
        if not path.exists():
            print(f"Not found: {path}")
            return 1
    sample_file = json.loads(sample_path.read_text(encoding="utf-8"))
    labels_file = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    if labels_file.get("sample_id") != sample_file["sample_id"]:
        print("These labels belong to a different sample.")
        return 1

    with connect(args.db) as conn:
        rows = conn.execute("SELECT * FROM runs WHERE batch = ?", (args.batch,)).fetchall()
    result = score(labels_file["labels"], sample_file["items"], {r["run_id"]: r for r in rows})

    print(f"Unlabeled: {result['unlabeled']}, unsure (excluded): {result['unsure']}")
    print(f"{'Group':18} {'n':>4} {'Agreement':>10} {'Kappa':>7}")
    for name, g in result["groups"].items():
        agreement = "n/a" if g["agreement"] is None else f"{g['agreement']:.0%}"
        kappa = "n/a" if g["kappa"] is None else f"{g['kappa']:.2f}"
        print(f"{name:18} {g['n']:>4} {agreement:>10} {kappa:>7}")
    c = result["confusion"]
    print("Confusion (rows: human, columns: judge)")
    print(f"  human pass: judge pass {c[('pass', 'pass')]}, judge fail {c[('pass', 'fail')]}")
    print(f"  human fail: judge pass {c[('fail', 'pass')]}, judge fail {c[('fail', 'fail')]}")
    if result["disagreements"]:
        print("Disagreements:")
        for d in result["disagreements"]:
            print(
                f"  {d['scenario_id']} [{d['split']}] human={d['human']} judge={d['judge']}"
                f" | run {d['run_id']}"
            )
            print(f"     judge: {d['rationale']}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from hebjudge.report import write_report

    if not Path(args.db).exists():
        print(f"No trace database at {args.db}. Run a scenario first.")
        return 1
    with connect(args.db) as conn:
        path = write_report(conn, args.out, batch=args.batch)
    print(f"Report written to {path}")
    return 0


def _target_test(args: argparse.Namespace) -> int:
    """Send one harmless message to a target and show the reply (v2 design, section 3)."""
    import uuid

    from dotenv import load_dotenv

    from hebjudge.targets import HELLO_MESSAGE, TargetError, build_target, load_target_file

    load_dotenv()
    try:
        target_file = load_target_file(args.config)
        target = build_target(target_file)
    except (ValueError, FileNotFoundError, TargetError) as exc:
        print(f"Error: {exc}")
        return 1

    message = args.message or HELLO_MESSAGE
    print(f"Target:  {target_file.name} ({target_file.target.adapter})")
    print(f"Sending: {message}")
    try:
        reply = target.send(message, session_id=f"hebjudge-test-{uuid.uuid4().hex[:8]}")
    except TargetError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Reply:   {reply.text}")
    if reply.tool_calls is None:
        print("Tools:   not visible (only the reply text can be checked)")
    else:
        calls = [(c.name, c.arguments) for c in reply.tool_calls]
        print(f"Tools:   {calls or 'none'}")
    print(f"Latency: {reply.latency_s:.2f} s")
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
    run_parser.add_argument("--workers", type=int, default=4, help="Runs executed in parallel")
    run_parser.add_argument(
        "--resume", action="store_true", help="Continue a batch, skipping runs already stored"
    )
    run_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))

    rejudge_parser = sub.add_parser(
        "rejudge", help="Re-evaluate stored runs with current scenarios and judge (no agent calls)"
    )
    rejudge_parser.add_argument("--batch", required=True, help="Batch to re-evaluate")
    rejudge_parser.add_argument("--new-batch", required=True, help="Label for the new records")
    rejudge_parser.add_argument("--scenarios", nargs="+", default=["data/scenarios"])
    rejudge_parser.add_argument("--only", nargs="+", help="Only these scenario ids")
    rejudge_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))

    calibrate = sub.add_parser("calibrate", help="Judge calibration against human labels (D-08)")
    calibrate_sub = calibrate.add_subparsers(dest="calibrate_command")
    sample_parser = calibrate_sub.add_parser(
        "sample", help="Pick a sample and build a labeling page"
    )
    sample_parser.add_argument("--batch", required=True)
    sample_parser.add_argument("--per-language", type=int, default=40)
    sample_parser.add_argument("--seed", type=int, default=20261115)
    sample_parser.add_argument("--scenarios", nargs="+", default=["data/scenarios"])
    sample_parser.add_argument("--force", action="store_true")
    sample_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    page_parser = calibrate_sub.add_parser(
        "page", help="Rebuild the labeling page from the existing sample (keeps labels)"
    )
    page_parser.add_argument("--batch", required=True)
    page_parser.add_argument("--scenarios", nargs="+", default=["data/scenarios"])
    page_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    score_parser = calibrate_sub.add_parser("score", help="Agreement and kappa vs. the judge")
    score_parser.add_argument("--batch", required=True)
    score_parser.add_argument("--labels", required=True, help="Labels JSON from the labeling page")
    score_parser.add_argument(
        "--sample", help="Sample file (default: data/labels/sample-BATCH.json)"
    )
    score_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))

    report_parser = sub.add_parser("report", help="Build an HTML report from saved traces")
    report_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    report_parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    report_parser.add_argument("--batch", default=None, help="Only include runs from this batch")

    target = sub.add_parser("target", help="Work with an agent under test (v2)")
    target_sub = target.add_subparsers(dest="target_command")
    target_test_parser = target_sub.add_parser(
        "test", help="Send one harmless message to the agent and show its reply"
    )
    target_test_parser.add_argument("config", help="Target YAML file")
    target_test_parser.add_argument("--message", help="Message to send instead of the default")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "rejudge":
        return _rejudge(args)
    if args.command == "report":
        return _report(args)
    if args.command == "calibrate" and args.calibrate_command == "sample":
        return _calibrate_sample(args)
    if args.command == "calibrate" and args.calibrate_command == "page":
        return _calibrate_page(args)
    if args.command == "calibrate" and args.calibrate_command == "score":
        return _calibrate_score(args)
    if args.command == "target" and args.target_command == "test":
        return _target_test(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
