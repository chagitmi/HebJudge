"""The local UI: a small web server on 127.0.0.1 and a Hebrew single-page app (D-45).

Standard library only. Nothing is hosted: the page and the data stay on the user's computer.
Every API call must carry a random token that is generated at start-up and given only to the
page, so that other websites open in the same browser cannot drive the server.
"""

import json
import re
import secrets
import threading
import traceback
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from hebjudge import __version__, plain, scan, settings, wizard
from hebjudge.compare import batch_verdicts, compare
from hebjudge.fixes import suggest
from hebjudge.judge import JUDGE_MODEL
from hebjudge.profile import new_canary
from hebjudge.report import final_verdict
from hebjudge.schema import load_scenarios
from hebjudge.targets import HELLO_MESSAGE, TargetError, TargetFile, build_target
from hebjudge.targets.config import (
    LITERAL_SECRET_MESSAGE,
    literal_secret_headers,
    load_target_file,
)
from hebjudge.templates import load_templates
from hebjudge.trace_store import DEFAULT_DB_PATH, RunRecord, connect, record_from_row

STATIC_DIR = Path(__file__).parent / "static"

# The page may load only its own files, and only talk to this server (D-49). Inline styles stay
# allowed: the page sets a few sizes with style attributes; inline scripts do not.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

# What the person reads when a request goes wrong; the details stay out of the page (D-49).
WRONG_ADDRESS = "אפשר לפתוח את HebJudge רק מהמחשב הזה, בכתובת שמופיעה בחלון הטרמינל."
OLD_PAGE = "הדף הזה נפתח לפני ש-HebJudge הופעל מחדש. מרעננים את הדף (F5) ומנסים שוב."
BAD_REQUEST = "הבקשה לא הגיעה כמו שצריך. מרעננים את הדף (F5) ומנסים שוב."
UNEXPECTED = (
    "משהו השתבש. מרעננים את הדף (F5) ומנסים שוב. אם זה חוזר, הפרטים הטכניים מופיעים בחלון הטרמינל."
)
TARGET_DIRS = (Path("targets"), Path("examples") / "targets")  # searched for target files
NEW_TARGETS_DIR = Path("targets")  # where the UI saves new target files
CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --- running scans in the background -----------------------------------------


@dataclass
class ScanJob:
    batch: str
    target_name: str
    total: int
    state: str = "running"  # running | done | error
    items: list[dict] = field(default_factory=list)
    errors: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    first_run_error: str | None = None  # why runs failed, shown when none succeeded
    stopped: bool = False
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)


class App:
    """The server's state: where data lives, and the scans started from the UI."""

    def __init__(self, root: Path, db_path: Path) -> None:
        self.root = root
        self.db_path = db_path
        self.token = secrets.token_urlsafe(24)
        self.jobs: dict[str, ScanJob] = {}

    # Paths --------------------------------------------------------------------

    def resolve(self, relative: str) -> Path:
        """A target path the UI may read or write: a .yaml file inside the project folder."""
        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents or path.suffix not in (".yaml", ".yml"):
            raise ApiError("אפשר לפתוח רק קובצי yaml מתוך תיקיית הפרויקט.")
        return path

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    # Targets --------------------------------------------------------------------

    def list_targets(self) -> list[dict]:
        targets = []
        for directory in TARGET_DIRS:
            for path in sorted((self.root / directory).glob("*.yaml")):
                entry: dict[str, Any] = {
                    "path": self.relative(path),
                    "example": "examples" in path.parts,
                }
                try:
                    target_file = load_target_file(path)
                    entry.update(
                        name=target_file.name,
                        adapter=target_file.target.adapter,
                        has_profile=target_file.profile is not None,
                    )
                except ValueError as exc:
                    entry.update(name=path.stem, error=str(exc).splitlines()[0])
                targets.append(entry)
        return targets

    def load(self, relative: str) -> TargetFile:
        path = self.resolve(relative)
        if not path.is_file():
            raise ApiError("הקובץ של הבוט לא נמצא. אולי הוא נמחק או הועבר.", 404)
        try:
            return load_target_file(path)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

    def save_target(self, data: dict, relative: str | None) -> str:
        try:
            target_file = TargetFile.model_validate(data)
        except ValueError as exc:
            raise ApiError(_pydantic_message(exc)) from exc
        if literal_secret_headers(getattr(target_file.target, "headers", None) or {}):
            raise ApiError(LITERAL_SECRET_MESSAGE)
        if relative:
            path = self.resolve(relative)
            if "examples" in path.parts:
                raise ApiError("אי אפשר לשנות את קובצי הדוגמה. שומרים בשם חדש.")
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", target_file.name.lower()).strip("-") or "agent"
            path = self.root / NEW_TARGETS_DIR / f"{slug}.yaml"
            n = 2
            while path.exists():
                path = self.root / NEW_TARGETS_DIR / f"{slug}-{n}.yaml"
                n += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = target_file.model_dump(mode="json", exclude_none=True)
        header = (
            "# Created with the HebJudge UI. Secrets go in environment variables, never here.\n"
        )
        text = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, width=100)
        path.write_text(header + text, encoding="utf-8")
        return self.relative(path)

    # Scans ----------------------------------------------------------------------

    def plan(self, body: dict) -> tuple[TargetFile, list, scan.Level, list, scan.CostEstimate]:
        target_file = self.load(body["path"])
        if target_file.profile is None:
            raise ApiError("לקובץ הזה אין פרופיל, וסריקה צריכה פרופיל")
        level = scan.LEVELS.get(body.get("level", "quick"))
        if level is None:
            raise ApiError("עומק הבדיקה לא מוכר.")
        templates = load_templates()
        goals = body.get("goals")
        if goals:
            templates = [t for t in templates if t.attacker_goal in goals]
        try:
            scenarios, skipped = scan.select_scenarios(
                target_file.profile, templates, level, body.get("languages") or None
            )
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        if not scenarios:
            raise ApiError("לא נוצרו תרחישים מהפרופיל הזה")
        estimate = scan.estimate_cost(target_file, len(scenarios) * level.repeats)
        return target_file, scenarios, level, skipped, estimate

    def start_scan(self, body: dict) -> str:
        if not settings.key_status()["set"]:
            raise ApiError("חסר מפתח OpenAI לשופט. מוסיפים אותו במסך הפתיחה, או בהגדרות.")
        target_file, scenarios, level, _, estimate = self.plan(body)
        permissions = self.db_path.parent / "permissions.json"
        if not scan.has_permission(permissions, target_file):
            if not body.get("confirm_permission"):
                raise ApiError("יש לאשר שהסוכן שלך או שיש לך הרשאה לבדוק אותו")
            scan.record_permission(permissions, target_file)
        max_cost = body.get("max_cost")
        if max_cost is not None and estimate.total_usd > float(max_cost):
            raise ApiError("הערכת העלות גבוהה מתקרת ההוצאה; לא נשלח כלום")
        try:
            build_target(target_file)  # fail now, before the background thread starts
        except (ValueError, TargetError) as exc:
            raise ApiError(str(exc)) from exc

        try:
            answers = wizard.load(self.root, body["path"])
        except ValueError:
            answers = None  # not a guided check: nothing to remember
        if answers is not None:
            answers.last_scan = {
                "level": level.name,
                "languages": body.get("languages"),
                "goals": body.get("goals"),
            }
            wizard.answers_path(self.root / body["path"]).write_text(
                json.dumps(answers.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        batch = f"scan-{stamp}-{uuid.uuid4().hex[:4]}"
        job = ScanJob(batch, target_file.name, len(scenarios) * level.repeats)
        self.jobs[batch] = job
        by_id = {s.id: s for s in scenarios}

        def on_result(index: int, total: int, record: RunRecord) -> None:
            with job.lock:
                job.items.append(_run_item(record, by_id.get(record.scenario_id)))
                job.cost_usd += record.cost_usd

        def on_error(index: int, total: int, scenario, model: str, exc: Exception) -> None:
            with job.lock:
                job.errors += 1
                if job.first_run_error is None:
                    job.first_run_error = f"{scenario.id}: {exc}"

        def work() -> None:
            try:
                outcome = scan.execute_scan(
                    target_file,
                    scenarios,
                    level,
                    batch,
                    self.db_path,
                    max_cost=float(max_cost) if max_cost is not None else None,
                    on_result=on_result,
                    on_error=on_error,
                    stop_event=job.stop_event,
                )
                job.stopped = outcome.stopped
                job.state = "done"
            except Exception as exc:  # shown to the user; the server keeps running
                job.error = str(exc)
                job.state = "error"

        threading.Thread(target=work, daemon=True).start()
        return batch

    def job_status(self, batch: str) -> dict:
        job = self.jobs.get(batch)
        if job is None:
            raise ApiError("הבדיקה הזו לא נמצאה.", 404)
        with job.lock:
            items = list(job.items)
            status = {
                "batch": batch,
                "target": job.target_name,
                "state": job.state,
                "total": job.total,
                "done": len(items) + job.errors,
                "errors": job.errors,
                "cost_usd": round(job.cost_usd, 4),
                "error": job.error,
                "first_run_error": job.first_run_error,
                "stopped": job.stopped,
                "items": items,
            }
        return status

    def scans(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT batch, agent_model, MIN(created_at) AS created, COUNT(*) AS runs, "
                "SUM(cost_usd) AS cost FROM runs WHERE agent_model LIKE 'target:%' "
                "GROUP BY batch ORDER BY created DESC"
            ).fetchall()
        return [
            {
                "batch": r["batch"],
                "target": r["agent_model"].removeprefix("target:"),
                "created": r["created"],
                "runs": r["runs"],
                "cost_usd": round(r["cost"] or 0, 4),
            }
            for r in rows
        ]

    def result(self, batch: str) -> dict:
        try:
            records, scenarios = scan.load_scan(self.db_path, batch)
        except ValueError as exc:
            raise ApiError(str(exc), 404) from exc
        by_id = {s.id: s for s in scenarios}
        goals = [
            {
                "goal": r.goal,
                "label": scan.GOAL_LABELS_HE.get(r.goal, r.label),
                "failed": r.failed,
                "total": r.total,
                "unclear": r.unclear,
            }
            for r in scan.summarize(records, scenarios)
        ]
        fixes = [
            {"he": f.suggestion.he, "en": f.suggestion.en, "scenarios": f.scenario_ids}
            for f in suggest(scan.failures(records, scenarios))
        ]
        rate = scan.attack_success_rate(records)
        items = [_run_item(r, by_id.get(r.scenario_id)) for r in records]
        return {
            **_plain_summary(items, suggest(scan.failures(records, scenarios))),
            "batch": batch,
            "target": records[0].agent_model.removeprefix("target:"),
            "created": records[0].created_at,
            "runs": len(records),
            "cost_usd": round(sum(r.cost_usd for r in records), 4),
            "attack_rate": None if rate is None else round(rate, 1),
            "goals": goals,
            "fixes": fixes,
            "items": items,
            "judge_model": JUDGE_MODEL,
        }

    # Guided checks ----------------------------------------------------------------------

    def save_wizard(self, data: dict, relative: str | None) -> str:
        try:
            answers = wizard.Answers.model_validate(data)
        except ValueError as exc:
            raise ApiError(wizard.friendly_error(exc)) from exc
        if answers.mode == "example" and not (self.root / wizard.EXAMPLE_TARGET).is_file():
            from hebjudge.examples_init import copy_examples

            copy_examples(self.root / "examples")
        try:
            return wizard.save(answers, self.root, relative)
        except ValueError as exc:
            raise ApiError(wizard.friendly_error(exc)) from exc

    def checks(self) -> list[dict]:
        """The guided checks, newest first, each with its last scan."""
        by_target: dict[str, dict] = {}
        for s in self.scans():
            by_target.setdefault(s["target"], s)
        found = []
        directory = self.root / wizard.WIZARD_DIR
        for answers_file in directory.glob("*" + wizard.ANSWERS_SUFFIX):
            target = answers_file.with_name(answers_file.name.removesuffix(wizard.ANSWERS_SUFFIX))
            target = target.with_suffix(".yaml")
            if not target.is_file():
                continue
            try:
                answers = wizard.Answers.model_validate_json(answers_file.read_text("utf-8"))
            except ValueError:
                continue
            last = by_target.get(answers.name)
            summary = None
            if last:
                try:
                    result = self.result(last["batch"])
                    summary = {k: result[k] for k in ("held", "failed", "attempts", "benign")}
                except ApiError:
                    summary = None
            found.append(
                {
                    "path": self.relative(target),
                    "name": answers.name,
                    "mode": answers.mode,
                    "last": last,
                    "summary": summary,
                    "modified": target.stat().st_mtime,
                }
            )
        return sorted(found, key=lambda c: -(c["modified"]))

    # Progress shown on the home screen ------------------------------------------------

    def progress_file(self) -> Path:
        return self.db_path.parent / "ui-progress.json"

    def progress(self) -> dict:
        """What the user has done that the data alone does not show (for now: comparisons)."""
        try:
            data = json.loads(self.progress_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        compared = data.get("compared") if isinstance(data, dict) else None
        return {"compared": [str(name) for name in compared] if isinstance(compared, list) else []}

    def _record_comparison(self, before: str, after: str) -> None:
        names = {s["batch"]: s["target"] for s in self.scans()}
        target = names.get(before)
        if target is None or target != names.get(after):
            return
        progress = self.progress()
        if target not in progress["compared"]:
            progress["compared"].append(target)
            self.progress_file().parent.mkdir(parents=True, exist_ok=True)
            self.progress_file().write_text(
                json.dumps(progress, ensure_ascii=False), encoding="utf-8"
            )

    def compare(self, before: str, after: str) -> dict:
        scans_dir = self.db_path.parent / "scans"
        goals: dict[str, str] = {}
        for batch in (before, after):
            if (scans_dir / batch).is_dir():
                for scenario in load_scenarios([scans_dir / batch]):
                    goals[scenario.id] = scenario.attacker_goal or "benign"
        try:
            with connect(self.db_path) as conn:
                result = compare(batch_verdicts(conn, before), batch_verdicts(conn, after), goals)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        self._record_comparison(before, after)
        return {
            "before": before,
            "after": after,
            "common": len(result.common),
            "goals": [
                {"goal": g, "label": scan.GOAL_LABELS_HE.get(g, g), **asdict(c)}
                for g, c in sorted(result.by_goal.items(), key=lambda item: item[0] == "benign")
            ],
            "fixed": result.fixed,
            "regressed": result.regressed,
            "other": [list(o) for o in result.other],
            "only_before": len(result.only_before),
            "only_after": len(result.only_after),
            "repeats": result.repeats,
        }


def _run_item(record: RunRecord, scenario) -> dict:
    verdict, decided_by = final_verdict(asdict(record))
    goal = (scenario.attacker_goal if scenario else None) or "benign"
    technique = scenario.technique if scenario else None
    tool_calls = json.loads(record.tool_calls)
    return {
        "scenario_id": record.scenario_id,
        "repeat": record.repeat_index + 1,
        "language": record.language,
        "category": record.category,
        "goal": (scenario.attacker_goal if scenario else None) or "benign",
        "technique": scenario.technique if scenario else None,
        "message": record.user_message,
        "reply": record.final_text,
        "tool_calls": tool_calls,
        "verdict": verdict,
        "decided_by": decided_by,
        "rationale": record.judge_rationale,
        "cost_usd": record.cost_usd,
        "plain": plain.attempt(goal, technique),
        "outcome": plain.outcome(goal, verdict),
    }


def _plain_summary(items: list[dict], fixes: list) -> dict:
    """The guided result: how many attempts the bot withstood, and one issue per fix."""
    decided = [i for i in items if i["verdict"] != "unclear"]
    attacks = [i for i in decided if i["goal"] != "benign"]
    benign = [i for i in decided if i["goal"] == "benign"]
    by_id: dict[str, dict] = {}
    for item in items:
        if item["verdict"] == "attack_succeeded":
            by_id.setdefault(item["scenario_id"], item)
    issues = []
    for fix in fixes:
        failed = [by_id[s] for s in fix.scenario_ids if s in by_id]
        if not failed:
            continue
        goals = [i["goal"] for i in failed]
        goal = max(set(goals), key=goals.count)
        first = next(i for i in failed if i["goal"] == goal)
        issues.append(
            {
                "goal": goal,
                "title": plain.GOAL_FAILED.get(goal, "הבוט נכשל"),
                "when": "" if goal == "benign" else plain.when(first["technique"]),
                "fix_he": fix.suggestion.he,
                "fix_en": fix.suggestion.en,
                "count": len(failed),
                "example": {"message": first["message"], "reply": first["reply"]},
            }
        )
    return {
        "attempts": len(decided),
        "held": sum(i["verdict"] != "attack_succeeded" for i in decided),
        "failed": sum(i["verdict"] == "attack_succeeded" for i in decided),
        "unclear": len(items) - len(decided),
        "attack_failures": sum(i["verdict"] == "attack_succeeded" for i in attacks),
        "benign": {
            "total": len(benign),
            "refused": sum(i["verdict"] == "attack_succeeded" for i in benign),
        },
        "issues": issues,
    }


def _pydantic_message(exc: Exception) -> str:
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    return "; ".join(lines[1:4]) if len(lines) > 1 else str(exc)


# --- HTTP ----------------------------------------------------------------------


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # keep the terminal quiet; errors are shown in the page

        # Responses ----------------------------------------------------------

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            charset = "" if content_type.startswith("font/") else "; charset=utf-8"
            self.send_header("Content-Type", f"{content_type}{charset}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, status: int = 200) -> None:
            self._send(
                status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json"
            )

        def _allowed_host(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        # Routing ------------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            if not self._allowed_host():
                self._json({"error": WRONG_ADDRESS}, 403)
                return
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                self._static(url.path)
                return
            self._api("GET", url.path, {k: v[0] for k, v in parse_qs(url.query).items()})

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed_host():
                self._json({"error": WRONG_ADDRESS}, 403)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:  # also covers a bad JSON body
                self._json({"error": BAD_REQUEST}, 400)
                return
            if not isinstance(body, dict):
                self._json({"error": BAD_REQUEST}, 400)
                return
            self._api("POST", urlparse(self.path).path, body)

        def _static(self, path: str) -> None:
            name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            file = (STATIC_DIR / name).resolve()
            if STATIC_DIR.resolve() not in file.parents or not file.is_file():
                self._send(404, b"not found", "text/plain")
                return
            content = file.read_bytes()
            if name == "index.html":
                content = content.replace(b"__HEBJUDGE_TOKEN__", app.token.encode())
                content = content.replace(b"__HEBJUDGE_VERSION__", __version__.encode())
            self._send(200, content, CONTENT_TYPES.get(file.suffix, "application/octet-stream"))

        def _api(self, method: str, path: str, data: dict) -> None:
            if not secrets.compare_digest(self.headers.get("X-HebJudge-Token", ""), app.token):
                self._json({"error": OLD_PAGE}, 403)
                return
            try:
                self._json(route(app, method, path, data))
            except ApiError as exc:
                self._json({"error": str(exc)}, exc.status)
            except (KeyError, TypeError, ValueError):
                self._json({"error": BAD_REQUEST}, 400)
            except Exception:  # noqa: BLE001 - the person gets a plain message, the terminal the details
                traceback.print_exc()
                self._json({"error": UNEXPECTED}, 500)

    return Handler


def route(app: App, method: str, path: str, data: dict) -> Any:
    if method == "GET" and path == "/api/state":
        return {
            "version": __version__,
            "targets": app.list_targets(),
            "scans": app.scans(),
            "progress": app.progress(),
            "key": settings.key_status(),
            "levels": {
                name: {"repeats": level.repeats, "templates": level.templates is None}
                for name, level in scan.LEVELS.items()
            },
        }
    if method == "GET" and path == "/api/settings":
        return settings.key_status()
    if method == "POST" and path == "/api/settings/key":
        try:
            settings.save_api_key(data["key"])
        except ValueError as exc:
            raise ApiError("זה לא נראה כמו מפתח של OpenAI (הוא מתחיל ב-sk-)") from exc
        return settings.key_status()
    if method == "POST" and path == "/api/settings/key/delete":
        settings.delete_api_key()
        return settings.key_status()
    if method == "POST" and path == "/api/settings/key/test":
        ok, detail = settings.test_api_key()
        return {"ok": ok, "detail": detail}
    if method == "POST" and path == "/api/init":
        from hebjudge.examples_init import copy_examples

        return {"written": len(copy_examples(app.root / "examples"))}
    if method == "GET" and path == "/api/target":
        target_file = app.load(data["path"])
        return {
            "path": data["path"],
            "data": target_file.model_dump(mode="json", exclude_none=True),
        }
    if method == "POST" and path == "/api/wizard/save":
        return {"path": app.save_wizard(data["answers"], data.get("path"))}
    if method == "GET" and path == "/api/wizard/load":
        try:
            answers = wizard.load(app.root, data["path"])
        except ValueError as exc:
            raise ApiError(str(exc), 404) from exc
        return {
            "path": data["path"],
            "answers": answers.model_dump(mode="json"),
            "tested_goals": answers.tested_goals,
        }
    if method == "GET" and path == "/api/wizard/checks":
        return {"checks": app.checks()}
    if method == "GET" and path == "/api/wizard/texts":
        return {
            "goals": [
                {"goal": g, "title": plain.GOAL_CHOICE[g][0], "hint": plain.GOAL_CHOICE[g][1]}
                for g in plain.GOALS
            ]
        }
    if method == "POST" and path == "/api/target/save":
        return {"path": app.save_target(data["data"], data.get("path"))}
    if method == "POST" and path == "/api/target/test":
        target_file = app.load(data["path"])
        try:
            reply = build_target(target_file).send(
                data.get("message") or HELLO_MESSAGE,
                session_id=f"hebjudge-ui-{uuid.uuid4().hex[:8]}",
            )
        except (ValueError, TargetError) as exc:
            raise ApiError(str(exc)) from exc
        return {
            "message": data.get("message") or HELLO_MESSAGE,
            "reply": reply.text,
            "tool_calls": None
            if reply.tool_calls is None
            else [{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
            "latency_s": round(reply.latency_s, 2),
        }
    if method == "POST" and path == "/api/canary":
        return {"canary": new_canary()}
    if method == "POST" and path == "/api/scan/plan":
        target_file, scenarios, level, skipped, estimate = app.plan(data)
        permissions = app.db_path.parent / "permissions.json"
        return {
            "target": target_file.name,
            "level": level.name,
            "scenarios": [
                {
                    "id": s.id,
                    "language": s.language,
                    "goal": s.attacker_goal or "benign",
                    "technique": s.technique,
                    "message": s.turns[0].content,
                    "plain": plain.attempt(s.attacker_goal, s.technique),
                }
                for s in scenarios
            ],
            "repeats": level.repeats,
            "runs": len(scenarios) * level.repeats,
            "estimate": {
                "judge_usd": estimate.judge_usd,
                "agent_usd": estimate.agent_usd,
                "total_usd": estimate.total_usd,
            },
            "skipped": [{"template": t, "reason": r} for t, r in skipped],
            "permission": scan.has_permission(permissions, target_file),
        }
    if method == "POST" and path == "/api/scan/start":
        return {"batch": app.start_scan(data)}
    if method == "POST" and path == "/api/scan/stop":
        job = app.jobs.get(data["batch"])
        if job is None:
            raise ApiError("הבדיקה הזו לא נמצאה.", 404)
        job.stop_event.set()
        return {"ok": True}
    if method == "GET" and path == "/api/scan/status":
        return app.job_status(data["batch"])
    if method == "GET" and path == "/api/scan/result":
        return app.result(data["batch"])
    if method == "GET" and path == "/api/compare":
        return app.compare(data["before"], data["after"])
    if method == "GET" and path == "/api/runs":
        with connect(app.db_path) as conn:
            rows = conn.execute("SELECT * FROM runs WHERE batch = ?", (data["batch"],)).fetchall()
        return [_run_item(record_from_row(r), None) for r in rows]
    raise ApiError("לא נמצא.", 404)


def serve(
    port: int = 8770, db_path: str | Path = DEFAULT_DB_PATH, open_browser: bool = True
) -> None:
    from hebjudge.settings import load_settings

    load_settings()
    app = App(Path.cwd(), Path(db_path))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"HebJudge UI: {url}")
    print("Runs on this computer only. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
